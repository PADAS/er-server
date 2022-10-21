from pulsar import arbiter, task, command, spawn, send

names = ['Angela', 'Chris', 'Molly', 'Emma', 'Swimmy', 'Bubbles']

@command()
def command1(request, message):
    echo = 'Hello {}!'.format(message['name'])
    request.actor.logger.info(echo)
    return echo

class Greeter:

    def __init__(self):
        a = arbiter()
        self._loop = a._loop
        self._loop.call_later(.5, self, None)
        a.start()
        print("started")

    @task
    def __call__(self, a=None):
        if a is None:
            actor = spawn(name='some-important-name')
            a = yield from actor
        if names:
            name = names.pop(0)
            send(a, 'command1', {'name': name})
            self._loop.call_later(.5, self, a)
        else:
            arbiter().stop()

if __name__ == '__main__':
    Greeter()
    print("ending")

