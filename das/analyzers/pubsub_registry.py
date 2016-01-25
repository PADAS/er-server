from das_server import celery
def new_observations_callback(body, message):

    print(message, body)
    source_id = body['source_id']

    print('sending task for analyzers.')
    celery.app.send_task('analyzers.tasks.handle_source', args=(source_id,))


PUBSUB_SUBSCRIPTIONS = (
    ('das.tracking.source.observations.new', new_observations_callback),
)