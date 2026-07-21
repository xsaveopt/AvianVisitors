<?php

declare(strict_types=1);

namespace AvianVisitors;

use AvianVisitors\Actions\ConfigController;
use AvianVisitors\Actions\DetectionsController;
use AvianVisitors\Actions\IllustrationController;
use AvianVisitors\Actions\MediaController;
use AvianVisitors\Actions\MenuController;
use AvianVisitors\Actions\StatusController;
use AvianVisitors\Actions\WikiController;
use AvianVisitors\Middleware\AuthMiddleware;
use AvianVisitors\Support\Conf;
use AvianVisitors\Support\MediaLocator;
use AvianVisitors\Support\SpeciesNames;
use Slim\App;
use Slim\Factory\AppFactory;

final class Kernel
{
    public static function create(Config $config): App
    {
        $app = AppFactory::create();
        $app->addRoutingMiddleware();
        $app->addBodyParsingMiddleware();

        $db = new Database($config->dbPath());
        $names = new SpeciesNames($config, $db);
        $media = new MediaLocator($config, $names);
        $conf = new Conf($config->confPath());
        $auth = new AuthMiddleware($config, $app->getResponseFactory());

        $detections = new DetectionsController($db);
        $wiki = new WikiController($config);
        $illustration = new IllustrationController($config);
        $publicIllustration = new IllustrationController($config, $db, true);
        $mediaController = new MediaController($media);
        $configController = new ConfigController($conf);
        $menu = new MenuController();
        $status = new StatusController($config);

        $app->get('/api/stats', [$detections, 'stats']);
        $app->get('/api/lifelist', [$detections, 'lifelist']);
        $app->get('/api/recent', [$detections, 'recent']);
        $app->get('/api/collage', [$detections, 'collage']);
        $app->get('/api/collage/recent', [$detections, 'collageRecent']);
        $app->get('/api/collage/illustration', $publicIllustration);
        $app->get('/api/species', [$detections, 'species']);
        $app->get('/api/timeseries', [$detections, 'timeseries']);
        $app->get('/api/firstseen', [$detections, 'firstseen']);
        $app->get('/api/wiki', $wiki);
        $app->get('/api/illustration', $illustration);
        $app->get('/api/theme', [$configController, 'theme']);

        $app->get('/api/recording', [$mediaController, 'recording'])->add($auth);
        $app->get('/api/spectrogram', [$mediaController, 'spectrogram'])->add($auth);
        $app->get('/api/config', [$configController, 'get'])->add($auth);
        $app->post('/api/config', [$configController, 'post'])->add($auth);
        $app->map(['GET', 'POST'], '/api/menu', $menu)->add($auth);
        $app->map(['GET', 'POST'], '/api/status', $status)->add($auth);

        $app->addErrorMiddleware(false, true, true);

        return $app;
    }
}
