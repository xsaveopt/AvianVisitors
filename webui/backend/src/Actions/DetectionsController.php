<?php

declare(strict_types=1);

namespace AvianVisitors\Actions;

use AvianVisitors\Database;
use AvianVisitors\Support\Json;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

final class DetectionsController
{
    public function __construct(
        private readonly Database $db,
    ) {}

    public function stats(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $total = (int) $this->db->value('SELECT COUNT(*) FROM detections');
        $species = (int) $this->db->value('SELECT COUNT(DISTINCT Sci_Name) FROM detections');
        $today = (int) $this->db->value("SELECT COUNT(*) FROM detections WHERE Date = DATE('now','localtime')");
        $todaySpec = (int) $this->db->value(
            "SELECT COUNT(DISTINCT Sci_Name) FROM detections WHERE Date = DATE('now','localtime')",
        );
        $lastHour = (int) $this->db->value(
            "SELECT COUNT(*) FROM detections WHERE Date = DATE('now','localtime') AND Time >= TIME('now','localtime','-1 hour')",
        );
        $week = (int) $this->db->value(
            "SELECT COUNT(*) FROM detections WHERE Date >= DATE('now','localtime','-7 day')",
        );
        $weekSpec = (int) $this->db->value(
            "SELECT COUNT(DISTINCT Sci_Name) FROM detections WHERE Date >= DATE('now','localtime','-7 day')",
        );
        /** @var string|null $started */
        $started = $this->db->value('SELECT MIN(Date) FROM detections');

        return Json::write($response, [
            'totals' => ['detections' => $total, 'species' => $species],
            'today' => ['detections' => $today, 'species' => $todaySpec],
            'last_hour' => ['detections' => $lastHour],
            'week' => ['detections' => $week, 'species' => $weekSpec],
            'started' => $started,
            'as_of' => date('c'),
        ]);
    }

    public function lifelist(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $rows = $this->db->rows(
            "SELECT Sci_Name AS sci, Com_Name AS com, MIN(Date||' '||Time) AS first_seen, "
            . "MAX(Date||' '||Time) AS last_seen, COUNT(*) AS n, MAX(Confidence) AS best_conf "
            . 'FROM detections GROUP BY Sci_Name ORDER BY first_seen ASC',
        );
        return Json::write($response, ['species' => $rows, 'as_of' => date('c')]);
    }

    public function recent(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $hours = max(1, min(1_000_000, (int) ($request->getQueryParams()['hours'] ?? 24)));
        $rows = $this->db->rows('SELECT Sci_Name AS sci, Com_Name AS com, COUNT(*) AS n, MAX(Confidence) AS best_conf, '
        . "MAX(Date||' '||Time) AS last_seen FROM detections "
        . "WHERE (julianday('now','localtime') - julianday(Date||' '||Time)) * 24 <= :hrs "
        . 'GROUP BY Sci_Name ORDER BY last_seen DESC', [':hrs' => $hours]);
        return Json::write($response, ['hours' => $hours, 'species' => $rows, 'as_of' => date('c')]);
    }

    public function collage(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $rows = $this->db->rows(
            'SELECT Sci_Name AS sci, Com_Name AS com, COUNT(*) AS n FROM detections '
            . "WHERE (julianday('now','localtime') - julianday(Date||' '||Time)) * 24 <= 24 "
            . 'GROUP BY Sci_Name ORDER BY n DESC',
        );
        return Json::write($response, ['species' => $rows]);
    }

    public function species(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $sci = (string) ($request->getQueryParams()['sci'] ?? '');
        if ($sci === '') {
            return Json::error($response, 'sci= required', 400);
        }
        $detections = $this->db->rows('SELECT Date AS d, Time AS t, File_Name AS file, Confidence AS conf '
        . 'FROM detections WHERE Sci_Name = :sn ORDER BY Date DESC, Time DESC LIMIT 500', [':sn' => $sci]);
        $summary = $this->db->one("SELECT Com_Name AS com, COUNT(*) AS total, MIN(Date||' '||Time) AS first_seen, "
        . "MAX(Date||' '||Time) AS last_seen, MAX(Confidence) AS best_conf "
        . 'FROM detections WHERE Sci_Name = :sn', [':sn' => $sci]);
        return Json::write($response, ['sci' => $sci, 'summary' => $summary, 'detections' => $detections]);
    }

    public function timeseries(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $days = max(1, min(90, (int) ($request->getQueryParams()['days'] ?? 30)));
        $daily = $this->db->rows(
            'SELECT Date AS date, COUNT(*) AS detections, COUNT(DISTINCT Sci_Name) AS species '
            . "FROM detections WHERE Date >= DATE('now','localtime','-"
            . ($days - 1)
            . " day') "
            . 'GROUP BY Date ORDER BY Date',
        );
        $byHour = $this->db->rows(
            "SELECT CAST(strftime('%H', Time) AS INT) AS hour, COUNT(*) AS detections "
            . "FROM detections WHERE Date >= DATE('now','localtime','-30 day') "
            . 'GROUP BY hour ORDER BY hour',
        );
        return Json::write($response, [
            'days' => $days,
            'daily' => $daily,
            'by_hour' => $byHour,
            'as_of' => date('c'),
        ]);
    }

    public function firstseen(Request $request, Response $response): Response
    {
        if (($guard = $this->guard($response)) !== null) {
            return $guard;
        }
        $limit = max(1, min(50, (int) ($request->getQueryParams()['limit'] ?? 10)));
        $rows = $this->db->rows("SELECT Sci_Name AS sci, Com_Name AS com, MIN(Date||' '||Time) AS first_seen, COUNT(*) AS total "
        . 'FROM detections GROUP BY Sci_Name ORDER BY first_seen DESC LIMIT :lim', [':lim' => $limit]);
        return Json::write($response, ['species' => $rows, 'as_of' => date('c')]);
    }

    private function guard(Response $response): ?Response
    {
        if (!$this->db->exists()) {
            return Json::error($response, 'birds.db not found', 503);
        }
        return null;
    }
}
