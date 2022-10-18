class SharedResourceHandler:
    def aquire_resource(self):
        raise NotImplementedError("aquire_resource")

    def release_resource(self):
        raise NotImplementedError("release_resource")

    def report_error(self, failure):
        raise NotImplementedError("report_error")
