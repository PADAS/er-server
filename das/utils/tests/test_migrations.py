from utils.migrations.subjects import SubjectSubTypeLoader


class TestSubjectSubTypeLoader:
    def test_subject_subtype_loader_doesnt_repeat_new_subtypes(self):
        loader_one = SubjectSubTypeLoader(subject_type_value="wildlife")
        loader_two = SubjectSubTypeLoader(subject_type_value="wildlife")

        assert loader_one._subject_subtypes is not loader_two._subject_subtypes
