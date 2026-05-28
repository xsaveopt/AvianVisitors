<?php
// AvianVisitors - drawer menu items.
//
// Returns the list of links shown in the side drawer when a user clicks
// the menu button. The live JS expects {items: [{label, href, native}]}.
//
// Default LAN deploy: returns items immediately, no auth.
// Forwarded deploy:  set AV_REQUIRE_AUTH=1 in /etc/avian/env (or in your
// php-fpm pool's env block) AND configure Caddy basic_auth on /avian/api/
// to force the lock screen.

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

// If forwarded mode is on AND no Basic-auth header arrived, 401 so the
// frontend shows the lock screen. The actual credential check is done
// by Caddy (basic_auth directive in forwarding/caddy-auth.caddy); this
// PHP only checks that *some* Authorization header reached us.
if (getenv('AV_REQUIRE_AUTH') === '1' && empty($_SERVER['HTTP_AUTHORIZATION'])) {
    http_response_code(401);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

// All hrefs are the canonical paths BirdNET-Pi's views.php recognises
// (lifted from homepage/views.php). AvianVisitors took over `/`, so
// the stock home is at /index.php.
echo json_encode([
    'items' => [
        ['label' => 'birdnet-pi', 'href' => '/index.php',                            'native' => false],
        ['label' => 'detections', 'href' => '/views.php?view=Todays+Detections',     'native' => false],
        ['label' => 'log',        'href' => '/views.php?view=View+Log',              'native' => false],
        ['label' => 'system',     'href' => '/views.php?view=Services',              'native' => false],
        ['label' => 'github',     'href' => 'https://github.com/Twarner491/AvianVisitors', 'native' => false],
    ],
]);
