from das_server import celery
def new_observations_callback(body, message):

    print(message, body)
    try:
        source_id = body.get('source_id')
    except:
        pass

    if not source_id:
        raise ValueError('''missing parameter 'source_id' in body''')

    print('sending task for analyzers.')
    celery.app.send_task('analyzers.tasks.handle_source', args=(source_id,))


PUBSUB_SUBSCRIPTIONS = (
    ('das.tracking.source.observations.new', new_observations_callback),
)