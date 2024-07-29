from typing import Any, Optional, Tuple
from uuid import UUID

from django.contrib.gis.db import models
from rest_framework.serializers import Serializer, UUIDField


class RankedTool:
    min_rank: float = 0
    max_rank: float = 1.0
    min_interval: float = 0.0001

    def __init__(self, instance: Any, before_key: Optional[UUID] = None) -> None:
        self.before_key_id = before_key

        self.instance = instance
        self.model = instance._meta.model
        self.queryset = self.model.objects.all().order_by("ordernum")
        self.order_list = []

    def get_first_value_to_insert(self) -> float:
        """
        Returns the first value to insert based on the ranked order.

        If the ranked order needs rebalancing, a full rebalance is performed
        before returning the new order value.

        Returns:
            float: The first value to insert.
        """
        new_order_value, need_rebalance = self._get_ranked_order()
        if need_rebalance:
            self.make_full_rebalance(queryset=self.queryset)
            new_order_value, _ = self._get_ranked_order()
        return new_order_value

    @classmethod
    def make_full_rebalance(cls, queryset: models.QuerySet) -> None:
        """
        Rebalances the ordernum field for all instances in the queryset.

        This method updates the ordernum field of each instance in the queryset
        to match their respective index position. It then performs a bulk update
        operation to efficiently update all instances in the database.

        Returns:
            None
        """
        objects_to_update = []
        for index, instance in enumerate(queryset, 1):
            instance.ordernum = index
            objects_to_update.append(instance)
        queryset.bulk_update(objects_to_update, ["ordernum"])

    def rank(self) -> None:
        if self.queryset.first().id == self.instance.id and not self.before_key_id:
            return None
        new_order_value, need_rebalance = self._get_ranked_order()
        if need_rebalance:
            self.make_full_rebalance(queryset=self.queryset)
            new_order_value, _ = self._get_ranked_order()
        self.instance.ordernum = new_order_value
        self.instance.save(update_fields=["ordernum"])

    def _get_ranked_order(self) -> Tuple[float, bool]:
        """
        Calculates a new order value based on the previous and next values.
        Returns:
            A tuple containing the new order value and a boolean indicating if the list needs a rebalance.
        """
        self.order_list = list(self.queryset.values_list("ordernum", flat=True))
        before_value, next_value = self._get_previous_and_next_values()

        if before_value is None:
            before_value = self.min_rank

        if next_value is None:
            next_value = self.max_rank

        if next_value - before_value < self.min_interval:
            return (before_value, True)

        mid_rank = (before_value + next_value) / 2

        if mid_rank in self.order_list or mid_rank < self.min_rank:
            return (mid_rank, True)
        return (mid_rank, False)

    def _get_previous_and_next_values(self) -> Tuple[Optional[float], Optional[float]]:
        before_value = None
        next_value = None
        if self.before_key_id is None:
            if self.order_list:
                next_value = self.order_list[0]
            return (before_value, next_value)

        before_value = self.queryset.get(id=self.before_key_id).ordernum
        new_index_to_insert = self.order_list.index(before_value) + 1
        try:
            next_value = self.order_list[new_index_to_insert]
        except IndexError:
            next_value = self.order_list[-1] + self.max_rank
        return (before_value, next_value)


class RankModelMixin(models.Model):
    ordernum = models.FloatField(default=0)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.ordernum:
            ranked_tool = RankedTool(instance=self, before_key=None)
            new_order_value = ranked_tool.get_first_value_to_insert()
            self.ordernum = new_order_value
        super().save(*args, **kwargs)


class RankSerializer(Serializer):
    before_key = UUIDField(required=True, allow_null=True)
