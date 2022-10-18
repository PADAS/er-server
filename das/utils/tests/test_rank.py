import pytest

from activity.models import EventCategory
from utils.rank import RankedTool


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRankedTool:
    @pytest.mark.parametrize(
        ("current_object_ordernum", "before_object_ordernum", "expected_ordernum"),
        (
            (2, 1.5, 1.75),
            (2, 1.5, 1.75),
            (4, 2, 3),
            (5, 3, 4),
            (6, 5, 5.5),
        ),
    )
    def test_make_rank_with_before_key(
        self, current_object_ordernum, before_object_ordernum, expected_ordernum
    ) -> None:
        current_obj = EventCategory.objects.create(value="current", display="Current", ordernum=current_object_ordernum)
        before_obj = EventCategory.objects.create(value="before", display="Before", ordernum=before_object_ordernum)

        ranked = RankedTool(instance=current_obj, before_key=before_obj.id)
        ranked.rank()

        assert current_obj.ordernum == expected_ordernum

    @pytest.mark.parametrize(
        ("current_object_ordernum", "expected_ordernum"),
        (
            (0.25, 0.25),
            (2, 0.5),
            (3.5, 0.5),
        ),
    )
    def test_make_rank_without_before_key(self, current_object_ordernum, expected_ordernum) -> None:
        current_obj = EventCategory.objects.create(value="current", display="Current", ordernum=current_object_ordernum)

        ranked = RankedTool(instance=current_obj, before_key=None)
        ranked.rank()

        assert current_obj.ordernum == expected_ordernum

    def test_move_first_to_last(self, five_event_categories) -> None:

        for ordernum, ec in enumerate(five_event_categories, 50):
            ec.ordernum = ordernum

        EventCategory.objects.bulk_update(five_event_categories, fields=["ordernum"])

        event_category = five_event_categories[0]
        insert_after = five_event_categories[4]

        ranked_tool = RankedTool(instance=event_category, before_key=insert_after.pk)
        ranked_tool.rank()

        for ec in five_event_categories:
            ec.refresh_from_db()

        assert event_category.ordernum > insert_after.ordernum
