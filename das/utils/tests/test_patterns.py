from utils.patterns import singleton


@singleton
class Foo:
    bar = "bar"


class TestSingletonPattern:
    def test_singleton_instance_is_unique(self):
        thing = Foo()
        other = Foo()

        assert thing is other
        assert thing.__class__.__name__ == "Foo"
