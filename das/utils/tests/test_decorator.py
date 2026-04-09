from unittest.mock import MagicMock, call

import pytest

from django.core.exceptions import ObjectDoesNotExist

from utils.decorator import retry_on_exception, use_shared_resource
from utils.interfaces import SharedResourceHandler


class CustomException(Exception):
    pass


class SharedResourceHandler(SharedResourceHandler):
    def __init__(self):
        self.resource = MagicMock()

    def aquire_resource(self):
        self.resource("aquire resource")

    def release_resource(self):
        self.resource("release resource")

    def report_error(self, failure):
        self.resource("error reported", str(failure))

    @use_shared_resource
    def successfull_use_of_resource(self):
        self.resource("using the resource")

    @use_shared_resource
    def unsuccessfull_use_of_resource(self):
        return 1 / 0

    @use_shared_resource
    def object_does_not_exist(self):
        raise ObjectDoesNotExist("SocketClient matching query does not exist.")


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


class TestUseSharedResource:
    def test_use_shared_resource_successfully(self):
        resource_handler = SharedResourceHandler()

        resource_handler.successfull_use_of_resource()

        assert resource_handler.resource.call_count == 3
        assert call("aquire resource") in resource_handler.resource.call_args_list
        assert call("using the resource") in resource_handler.resource.call_args_list
        assert call("release resource") in resource_handler.resource.call_args_list

    def test_use_shared_resource_unsuccessfully(self):
        resource_handler = SharedResourceHandler()

        with pytest.raises(ZeroDivisionError):
            resource_handler.unsuccessfull_use_of_resource()

        assert resource_handler.resource.call_count == 3
        assert call("aquire resource") in resource_handler.resource.call_args_list
        assert call("error reported", "division by zero") in resource_handler.resource.call_args_list
        assert call("release resource") in resource_handler.resource.call_args_list

    def test_object_does_not_exist_skips_report_error(self):
        resource_handler = SharedResourceHandler()

        with pytest.raises(ObjectDoesNotExist):
            resource_handler.object_does_not_exist()

        assert resource_handler.resource.call_count == 2
        assert call("aquire resource") in resource_handler.resource.call_args_list
        assert call("release resource") in resource_handler.resource.call_args_list
