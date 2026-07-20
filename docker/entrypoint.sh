#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/home/birdnet/BirdNET-Pi
DATA_DIR=/data
RECORDINGS=${DATA_DIR}/recordings
LOGS_DIR=${DATA_DIR}/logs
CFG_DIR=${DATA_DIR}/config
CONF=${DATA_DIR}/birdnet.conf
DB=${DATA_DIR}/birds.db
DBTXT=${DATA_DIR}/BirdDB.txt

UID_IN=$(id -u)
GID_IN=$(id -g)

PORTS_INTERNAL="8080 8081 8000 8501"
EXEC_MOUNTS=""
REQUIRED_RW="${DATA_DIR}"
ENV_REPORT="BIRDNET_REC_CARD BIRDNET_CHANNELS BIRDNET_LATITUDE BIRDNET_LONGITUDE RTSP_STREAM AV_ADMIN_USER AV_ADMIN_PASSWORD AV_PUBLIC_GALLERY AV_PUBLIC_PATH"
ENV_SECRET="AV_ADMIN_PASSWORD"
NET_DNS_TARGET="cloudflare.com"
NET_TCP_TARGET="1.1.1.1:443"

C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_GRN=$'\033[32m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
[ -t 1 ] || { C_RED=; C_YEL=; C_GRN=; C_DIM=; C_RST=; }

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log()  { printf '%s [avianvisitors] %s%s%s %s\n' "$(ts)" "$2" "$1" "$C_RST" "$3"; }
info() { log INFO  "$C_GRN" "$*"; }
warn() { log WARN  "$C_YEL" "$*"; }
err()  { log ERROR "$C_RED" "$*"; }
note() { printf '%s %s[avianvisitors]      %s%s\n' "$(ts)" "$C_DIM" "$*" "$C_RST"; }

FATAL=0
fail() { err "$*"; FATAL=1; }

map_host_id() {
  local want="$1" mapfile="$2"
  awk -v w="$want" '{ if (w>=$1 && w<$1+$3) { print $2+(w-$1); f=1; exit } } END { if(!f) print "?" }' "$mapfile" 2>/dev/null || echo '?'
}

USERNS=0
HOST_UID="${UID_IN}"
HOST_GID="${GID_IN}"
if [ -r /proc/self/uid_map ]; then
  read -r u0 h0 _ < /proc/self/uid_map
  if [ "${u0:-0}" != "0" ] || [ "${h0:-0}" != "0" ]; then
    USERNS=1
    HOST_UID=$(map_host_id "${UID_IN}" /proc/self/uid_map)
    HOST_GID=$(map_host_id "${GID_IN}" /proc/self/gid_map)
  fi
fi

mount_opt() {
  awk -v p="$1" -v o="$2" '$5==p { n=split($6,a,","); for(i=1;i<=n;i++) if(a[i]==o){print o; exit} }' /proc/self/mountinfo 2>/dev/null
}

is_system_fs() {
  case "$1" in
    proc|sysfs|cgroup|cgroup2|devpts|mqueue|tmpfs|overlay|devtmpfs|securityfs|bpf|tracefs|debugfs|fusectl|configfs|pstore|autofs|binfmt_misc|hugetlbfs|nsfs|fuse.lxcfs|ramfs|rpc_pipefs) return 0 ;;
  esac
  return 1
}

is_system_path() {
  case "$1" in
    /|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*|/run|/run/*|/etc/hostname|/etc/hosts|/etc/resolv.conf) return 0 ;;
  esac
  return 1
}

link() {
  local src="$1" dst="$2" parent
  parent=$(dirname "$dst")
  if [ ! -d "$parent" ] || [ ! -w "$parent" ]; then
    err "cannot create symlink ${dst}: directory ${parent} is missing or not writable by uid=${UID_IN}"
    exit 1
  fi
  ln -sfn "$src" "$dst"
}

is_required_rw() {
  case " ${REQUIRED_RW} " in *" $1 "*) return 0 ;; esac
  return 1
}

check_rw() {
  local dir="$1" label="$2" required=0
  is_required_rw "$dir" && required=1
  if [ ! -d "$dir" ]; then
    if [ "$required" = "1" ]; then fail "${label}: ${dir} is not present"; else warn "${label}: ${dir} is not present"; fi
    return
  fi
  local owner mode probe ro=
  owner=$(stat -c '%U:%G (%u:%g)' "$dir" 2>/dev/null || echo '?')
  mode=$(stat -c '%a' "$dir" 2>/dev/null || echo '?')
  [ "$(mount_opt "$dir" ro)" = ro ] && ro=' [mounted read-only]'
  probe="${dir}/.av-write-test.${RANDOM}"
  if [ -r "$dir" ] && touch "$probe" 2>/dev/null; then
    rm -f "$probe"
    info "${label}: read/write OK (${dir})"
    return
  fi
  if [ "$required" = "1" ]; then
    fail "${label}: cannot read+write ${dir} as uid=${UID_IN}"
  elif [ -n "$ro" ]; then
    note "${label}: ${dir} is read-only${ro}; skipping (fine if you mounted it ro on purpose)"
    return
  else
    warn "${label}: ${dir} is not writable by uid=${UID_IN}"
  fi
  note "current owner=${owner} mode=${mode}${ro}"
  if [ "${USERNS}" = "1" ]; then
    note "fix on host: chown -R ${HOST_UID}:${HOST_GID} <host-path-mounted-at-${dir}>"
  else
    note "fix on host: chown -R ${UID_IN}:${GID_IN} <host-path-mounted-at-${dir}>"
  fi
}

check_perms() {
  local dir="$1" mode others
  [ -d "$dir" ] || return 0
  mode=$(stat -c '%a' "$dir" 2>/dev/null || echo '')
  [ -z "$mode" ] && return
  others="${mode: -1}"
  case "$others" in
    2|3|6|7) warn "loose permissions on ${dir} (mode ${mode}, writable by any user); tighten to 0750/0770 unless this is intentional" ;;
  esac
}

check_flags() {
  local dir="$1"
  if [ "$(mount_opt "$dir" noexec)" = noexec ]; then
    case " ${EXEC_MOUNTS} " in
      *" ${dir} "*) warn "${dir} is mounted noexec but this app must execute files there; remove noexec from that mount" ;;
    esac
  fi
}

check_caps() {
  local hex val
  hex=$(awk '/^CapEff:/{print $2; exit}' /proc/self/status 2>/dev/null || echo '')
  if [ -z "$hex" ]; then note "capabilities: could not read /proc/self/status"; return; fi
  val=$((16#$hex))
  if [ "$val" -eq 0 ]; then note "capabilities: all dropped (CapEff=${hex}); good"; return; fi
  local names="0:chown 1:dac_override 2:dac_read_search 3:fowner 4:fsetid 5:kill 6:setgid 7:setuid 8:setpcap 9:linux_immutable 10:net_bind_service 11:net_broadcast 12:net_admin 13:net_raw 14:ipc_lock 16:sys_module 17:sys_rawio 18:sys_chroot 19:sys_ptrace 21:sys_admin 22:sys_boot 24:sys_resource 25:sys_time 27:mknod 29:audit_write 31:setfcap 38:perfmon 39:bpf"
  local default=" 0 1 3 4 5 6 7 8 10 13 18 27 29 31 "
  local extra='' base='' e bit name
  for e in $names; do
    bit="${e%%:*}"; name="${e#*:}"
    if (( (val >> bit) & 1 )); then
      case "$default" in *" $bit "*) base="${base} ${name}" ;; *) extra="${extra} ${name}" ;; esac
    fi
  done
  if [ -n "$extra" ]; then
    warn "elevated capabilities present beyond the docker default:${extra}"
    note "if the app does not need these, drop them (cap_drop) to shrink the attack surface"
  else
    note "capabilities: docker default set only (${base# })"
  fi
}

check_clock() {
  local year
  year=$(date -u +%Y 2>/dev/null || echo 0)
  if [ "${year:-0}" -lt 2024 ]; then
    warn "system clock looks wrong (UTC year=${year}); TLS, tokens and scheduling may misbehave"
  fi
  if [ -z "${TZ:-}" ] && [ ! -e /etc/localtime ]; then
    note "timezone not configured (TZ unset, no /etc/localtime); timestamps will be UTC"
  fi
}

is_secret() {
  case " ${ENV_SECRET} " in *" $1 "*) return 0 ;; esac
  return 1
}

report_env() {
  note "configuration (environment overrides; blank means default/config file):"
  local v val shown
  for v in ${ENV_REPORT}; do
    val="${!v:-}"
    if [ -z "$val" ]; then
      shown='- (unset)'
    elif is_secret "$v"; then
      shown='****** (set)'
    else
      shown="$val"
    fi
    printf '%s %s[avianvisitors]        %-20s %s%s\n' "$(ts)" "$C_DIM" "$v" "$shown" "$C_RST"
  done
}

listening_ports() {
  awk '$4=="0A"{n=split($2,a,":"); print a[2]}' /proc/net/tcp /proc/net/tcp6 2>/dev/null \
    | while read -r h; do [ -n "$h" ] && printf '%d\n' "0x$h"; done | sort -un
}

check_ports() {
  local held p
  held=$(listening_ports)
  for p in ${PORTS_INTERNAL}; do
    if printf '%s\n' "$held" | grep -qx "$p"; then
      warn "port ${p} is already in use before services start; a service may fail to bind"
      note "this usually means network_mode: host with another process on ${p}; remap or stop the conflict"
    fi
  done
}

check_net() {
  [ "${PREFLIGHT_NET_CHECK:-0}" = "1" ] || return 0
  local host="${NET_TCP_TARGET%:*}" port="${NET_TCP_TARGET##*:}"
  if getent hosts "${NET_DNS_TARGET}" >/dev/null 2>&1; then
    info "outbound DNS OK (resolved ${NET_DNS_TARGET})"
  else
    warn "outbound DNS failed (could not resolve ${NET_DNS_TARGET}); name resolution may be broken"
  fi
  if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
    info "outbound TCP OK (connected ${host}:${port})"
  else
    warn "outbound TCP to ${host}:${port} failed; egress may be blocked"
  fi
}

collect_mounts() {
  declare -A seen
  MOUNTS=()
  local mp fstype
  seen["${DATA_DIR}"]=1
  MOUNTS+=("${DATA_DIR}")
  while IFS=$'\t' read -r mp fstype; do
    [ -z "$mp" ] && continue
    [ -n "${seen[$mp]:-}" ] && continue
    is_system_fs "$fstype" && continue
    is_system_path "$mp" && continue
    seen["$mp"]=1
    MOUNTS+=("$mp")
  done < <(awk '{ s=0; for(i=1;i<=NF;i++) if($i=="-"){s=i;break} if(s) print $5 "\t" $(s+1) }' /proc/self/mountinfo 2>/dev/null)
}

info "starting preflight checks"
if [ "${UID_IN}" = "0" ]; then
  warn "running as uid=0 (root); this image is built to run unprivileged"
else
  note "all processes run as uid=${UID_IN} gid=${GID_IN} (non-root)"
fi
if [ "${USERNS}" = "1" ]; then
  warn "user namespace remapping is active (rootless docker or userns-remap)"
  note "inside uid=${UID_IN} maps to HOST uid=${HOST_UID}; inside gid=${GID_IN} maps to HOST gid=${HOST_GID}"
  note "when fixing bind-mount ownership on the host, chown to the HOST ids above, not ${UID_IN}:${GID_IN}"
fi

check_caps
check_clock
report_env

collect_mounts
for m in "${MOUNTS[@]}"; do
  if is_required_rw "$m"; then label="data volume"; else label="bind mount ${m}"; fi
  check_rw "$m" "$label"
  check_perms "$m"
  check_flags "$m"
done

if [ "${FATAL}" = "1" ]; then
  err "preflight failed: required volumes are not writable; refusing to start"
  note "this container runs as a non-root user and does not change ownership of your mounts"
  note "if you bind-mount host folders, fix their ownership with the chown shown above, then restart"
  note "if you use named docker volumes (the default compose setup), recreate them: docker compose down -v && docker compose up -d"
  exit 1
fi

check_ports
check_net

mkdir -p \
  "${RECORDINGS}/Extracted/By_Date" \
  "${RECORDINGS}/Extracted/Charts" \
  "${RECORDINGS}/Processed" \
  "${RECORDINGS}/StreamData" \
  "${LOGS_DIR}" \
  "${CFG_DIR}"

link "${CONF}" "${APP_DIR}/birdnet.conf"
link "${CONF}" /etc/birdnet/birdnet.conf

for f in apprise.txt body.txt IdentifiedSoFar.txt include_species_list.txt exclude_species_list.txt whitelist_species_list.txt; do
  link "${CFG_DIR}/${f}" "${APP_DIR}/${f}"
done

if [ ! -f "${CONF}" ]; then
  info "no config found; generating ${CONF} (details in ${LOGS_DIR}/install_config.log)"
  if ! HOME=/home/birdnet USER=birdnet HOSTNAME="$(hostname)" my_dir="${APP_DIR}" \
       bash "${APP_DIR}/birdnet/install_config.sh" >"${LOGS_DIR}/install_config.log" 2>&1; then
    err "config generation failed; see ${LOGS_DIR}/install_config.log"
    exit 1
  fi
fi

[ -n "${BIRDNET_REC_CARD:-}" ]   && sed -i "s|^REC_CARD=.*|REC_CARD=${BIRDNET_REC_CARD}|"   "${CONF}"
[ -n "${BIRDNET_CHANNELS:-}" ]   && sed -i "s|^CHANNELS=.*|CHANNELS=${BIRDNET_CHANNELS}|"   "${CONF}"
[ -n "${BIRDNET_LATITUDE:-}" ]   && sed -i "s|^LATITUDE=.*|LATITUDE=${BIRDNET_LATITUDE}|"   "${CONF}"
[ -n "${BIRDNET_LONGITUDE:-}" ]  && sed -i "s|^LONGITUDE=.*|LONGITUDE=${BIRDNET_LONGITUDE}|" "${CONF}"

set -a
source "${CONF}"
set +a

if [ -d "${APP_DIR}/webui" ]; then
  link "${APP_DIR}/webui"                            "${EXTRACTED}/webui"
  link "${APP_DIR}/webui/frontend/dist/index.html"   "${EXTRACTED}/index.html"
  link "${APP_DIR}/webui/frontend/dist/assets"       "${EXTRACTED}/assets"
  link "${APP_DIR}/webui/frontend/dist/nest.webp"    "${EXTRACTED}/nest.webp"
  link "${APP_DIR}/webui/frontend/dist/favicon.png"  "${EXTRACTED}/favicon.png"
  link "${APP_DIR}/webui/frontend/dist/favicon.png"  "${EXTRACTED}/favicon.ico"
fi

ln -sf "${APP_DIR}/birdnet/model/labels.txt" "${APP_DIR}/birdnet/labels.txt" 2>/dev/null || true
ln -sf "${APP_DIR}/birdnet/model/labels_nm/labels_en.txt" "${APP_DIR}/birdnet/model/labels_flickr.txt" 2>/dev/null || true

if ls "${APP_DIR}"/birdnet/model/*.tflite >/dev/null 2>&1; then
  info "detection model present"
else
  fail "no .tflite model found under ${APP_DIR}/birdnet/model; detection cannot run"
fi

link "${DB}" "${APP_DIR}/birdnet/birds.db"
if [ ! -f "${DB}" ]; then
  info "no database found; creating ${DB} (details in ${LOGS_DIR}/createdb.log)"
  if ! HOME=/home/birdnet USER=birdnet bash "${APP_DIR}/birdnet/createdb.sh" >"${LOGS_DIR}/createdb.log" 2>&1; then
    err "database creation failed; see ${LOGS_DIR}/createdb.log"
    exit 1
  fi
fi

link "${DBTXT}" "${APP_DIR}/BirdDB.txt"
if [ ! -f "${DBTXT}" ]; then
  echo "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap" > "${DBTXT}"
fi

REC_CARD_VAL="${REC_CARD:-default}"
AUDIO_OK=false
if [ -n "${RTSP_STREAM:-}" ]; then
  info "audio source: RTSP stream configured; recording will use the network feed"
  AUDIO_OK=true
elif [ ! -d /dev/snd ]; then
  warn "no audio devices: /dev/snd is not present in the container; recording is disabled"
  note "map your sound card in docker-compose.yml: devices: [ \"/dev/snd:/dev/snd\" ]"
else
  snd_gid=$(stat -c '%g' /dev/snd/timer /dev/snd/control* 2>/dev/null | sort -un | head -1 || true)
  audio_gid=$(getent group audio | cut -d: -f3 || true)
  readable=0
  for node in /dev/snd/pcmC*c /dev/snd/controlC*; do
    [ -e "$node" ] || continue
    if [ -r "$node" ]; then readable=1; break; fi
  done
  cards=$(arecord -l 2>/dev/null | grep -c '^card ' || true)
  if [ "${readable}" = "1" ] && [ "${cards:-0}" -ge 1 ]; then
    info "microphone access OK (${cards} capture device(s) visible, configured REC_CARD=${REC_CARD_VAL})"
    AUDIO_OK=true
  elif [ "${cards:-0}" -ge 1 ] && [ "${readable}" != "1" ]; then
    warn "capture devices exist but uid=${UID_IN} cannot read /dev/snd nodes; recording will fail"
    note "/dev/snd is owned by gid=${snd_gid:-?}; container audio gid=${audio_gid:-?}; current groups: $(id -Gn | tr ' ' ',')"
    note "fix in docker-compose.yml by granting the host audio gid: group_add: [ \"${snd_gid:-29}\" ]"
  else
    warn "no usable capture device found (REC_CARD=${REC_CARD_VAL}); recording will fail until a mic is available"
    note "list cards the container can see with: docker compose exec avianvisitors arecord -l"
    note "then set the right one via BIRDNET_REC_CARD (e.g. \"plughw:1,0\") in docker-compose.yml"
  fi
fi

if [ "${AUDIO_OK}" = "true" ] && [ -z "${RTSP_STREAM:-}" ] && [ -d /dev/snd ]; then
  hw=""
  case "${REC_CARD:-default}" in
    plughw:* | hw:*) hw="hw:${REC_CARD#*:}" ;;
    [0-9]*,[0-9]*) hw="hw:${REC_CARD}" ;;
  esac
  if [ -z "${hw}" ]; then
    hw=$(arecord -l 2>/dev/null | sed -n 's/^card \([0-9]\+\):.*device \([0-9]\+\):.*/hw:\1,\2/p' | head -1 || true)
  fi
  if [ -n "${hw}" ]; then
    cat > /home/birdnet/.asoundrc <<EOF
pcm.birdnet_mic {
  type plug
  slave.pcm "dsnoop_birdnet"
}
pcm.dsnoop_birdnet {
  type dsnoop
  ipc_key 2048
  ipc_perm 0660
  slave {
    pcm "${hw}"
    channels ${CHANNELS:-2}
    rate 48000
    format S16_LE
  }
}
EOF
    sed -i "s|^REC_CARD=.*|REC_CARD=birdnet_mic|" "${CONF}"
    info "shared capture enabled: recording + livestream both read ${hw} via dsnoop"
    note "if recording fails to open the mic, your card may not support 48000Hz/${CHANNELS:-2}ch; set BIRDNET_REC_CARD to a raw plughw device and live audio will be disabled"
  else
    warn "could not resolve the capture hw device; recording + livestream cannot share a raw device, so live audio will conflict with recording"
  fi
fi

export AV_AUDIO_AUTOSTART="${AUDIO_OK}"
if [ "${AUDIO_OK}" != "true" ]; then
  warn "recording + analysis will not auto-start without an audio source; the rest of the app runs normally"
  note "connect a mic (or set RTSP_STREAM), then start them from the web UI tools or restart the container"
fi

disk_free_mb() { df -Pm "$1" 2>/dev/null | awk 'NR==2 {print $4}'; }
free_mb=$(disk_free_mb "${DATA_DIR}")
if [ -n "${free_mb:-}" ] && [ "${free_mb}" -lt 500 ]; then
  warn "low disk space: only ${free_mb} MB free on ${DATA_DIR}; recordings/db may fail (FULL_DISK=${FULL_DISK:-purge}, PURGE_THRESHOLD=${PURGE_THRESHOLD:-95})"
fi

if [ -z "${LATITUDE:-}" ] || [ -z "${LONGITUDE:-}" ] || [ "${LATITUDE:-0}" = "0" ]; then
  warn "location not set (LATITUDE/LONGITUDE empty); species range filtering will be inaccurate"
  note "set BIRDNET_LATITUDE / BIRDNET_LONGITUDE in docker-compose.yml"
fi

if [ -f /etc/icecast2/icecast.xml ]; then
  ICE_PWD_VAL="${ICE_PWD:-birdnetpi}"
  sed -i "s/>admin</>birdnet</g" /etc/icecast2/icecast.xml
  sed -i "s|<logdir>.*</logdir>|<logdir>${LOGS_DIR}</logdir>|" /etc/icecast2/icecast.xml
  for prefix in source- relay- admin- master- ""; do
    sed -i "s|<${prefix}password>.*</${prefix}password>|<${prefix}password>${ICE_PWD_VAL}</${prefix}password>|g" /etc/icecast2/icecast.xml
  done
fi

append_public_gallery() {
  if [ "${AV_PUBLIC_GALLERY:-false}" != "true" ]; then
    note "public gallery disabled (set AV_PUBLIC_GALLERY=true to serve the last-24h collage on port 8081)"
    return
  fi

  local raw sub pub
  raw=$(printf '%s' "${AV_PUBLIC_PATH:-}" | tr -cd 'A-Za-z0-9/_-')
  raw="${raw#/}"
  raw="${raw%/}"
  if [ -n "$raw" ]; then sub="/${raw}"; else sub=""; fi

  pub=/home/birdnet/run/public.html
  cp "${APP_DIR}/webui/frontend/dist/public.html" "$pub"
  sed -i "s|__AV_BASE_PATH__|${sub}|g" "$pub"
  link "$pub" "${EXTRACTED}/public.html"

  if [ -z "$sub" ]; then
    cat >> "${CADDY_OUT}" <<'EOF'

:8081 {
	root * /home/birdnet/BirdSongs/Extracted

	handle /api/collage* {
		php_fastcgi unix//run/php/php-fpm.sock {
			try_files /webui/backend/public/index.php
		}
	}
	handle /assets/* {
		file_server
	}
	@pubfiles path /favicon.png /favicon.ico /nest.webp
	handle @pubfiles {
		file_server
	}
	handle / {
		rewrite * /public.html
		file_server
	}
	handle {
		respond 404
	}
}
EOF
    info "public gallery enabled on port 8081 at / (last 24h collage only)"
  else
    cat >> "${CADDY_OUT}" <<EOF

:8081 {
	root * /home/birdnet/BirdSongs/Extracted

	handle ${sub}/api/collage* {
		uri strip_prefix ${sub}
		php_fastcgi unix//run/php/php-fpm.sock {
			try_files /webui/backend/public/index.php
		}
	}
	handle ${sub}/assets/* {
		uri strip_prefix ${sub}
		file_server
	}
	@pubfiles path ${sub}/favicon.png ${sub}/favicon.ico ${sub}/nest.webp
	handle @pubfiles {
		uri strip_prefix ${sub}
		file_server
	}
	handle ${sub} {
		redir ${sub}/ 308
	}
	handle ${sub}/ {
		rewrite * /public.html
		file_server
	}
	handle {
		respond 404
	}
}
EOF
    info "public gallery enabled on port 8081 at ${sub}/ (last 24h collage only)"
  fi
}

CADDY_TMPL=/etc/caddy/Caddyfile.tmpl
CADDY_OUT=/etc/caddy/Caddyfile
if [ -n "${AV_ADMIN_PASSWORD:-}" ] && [ -z "${AV_ADMIN_USER:-}" ]; then
  warn "AV_ADMIN_PASSWORD is set but AV_ADMIN_USER is empty: set both to enable auth; staying PUBLIC until you do"
fi
if [ -n "${AV_ADMIN_PASSWORD:-}" ] && [ -n "${AV_ADMIN_USER:-}" ]; then
  AV_USER="${AV_ADMIN_USER}"
  AV_HASH=$(php -r 'echo password_hash($argv[1], PASSWORD_BCRYPT);' "${AV_ADMIN_PASSWORD}")
  cat > "${CADDY_OUT}" <<EOF
{
	admin off
	auto_https off
}

:8080 {
	root * /home/birdnet/BirdSongs/Extracted

	@protected path /stream /stats /stats/* /By_Date /By_Date/* /Charts /Charts/* /StreamData /StreamData/* /Processed /Processed/*
	basic_auth @protected {
		${AV_USER} ${AV_HASH}
	}

	handle /stream {
		reverse_proxy localhost:8000
	}
	handle /stats* {
		reverse_proxy localhost:8501
	}

	handle /api/* {
		php_fastcgi unix//run/php/php-fpm.sock {
			try_files /webui/backend/public/index.php
		}
	}

	handle /By_Date* {
		file_server browse
	}
	handle /Charts* {
		file_server browse
	}
	handle /StreamData* {
		file_server browse
	}
	handle /Processed* {
		file_server browse
	}

	handle {
		try_files {path} /index.html
		file_server
	}
}
EOF
  info "admin auth enabled (user=${AV_USER}); protected: recordings, livestream, stats, file browse, admin api"
else
  cp "${CADDY_TMPL}" "${CADDY_OUT}"
  warn "admin auth disabled; recordings, livestream, stats and admin tools are PUBLIC (set both AV_ADMIN_USER and AV_ADMIN_PASSWORD to enable)"
fi

append_public_gallery

info "preflight complete; launching services"
exec "$@"
