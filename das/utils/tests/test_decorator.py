import pytest

from utils.decorator import retry_on_exception


class CustomException(Exception):
    pass


class TestFunctionRetryOnException:
    def test_retries_exausted(self):
        @retry_on_exception(exception_type=CustomException, delay=0)
        def always_fail():
            raise CustomException("This function fails always")

        with pytest.raises(CustomException):
            always_fail()

    def test_function_succeed_after_failure(self):
        counter = 0

        @retry_on_exception(exception_type=CustomException, delay=0)
        def succeed_eventually():
            nonlocal counter
            should_fail = counter == 0
            counter += 1

            if should_fail:
                raise CustomException("This time I fail")

            return True

        succeed = succeed_eventually()

        assert succeed
