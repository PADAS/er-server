import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.contrib.gis.db.models import QuerySet


class HashByModelBuilder:
    """
    A class that builds a hash string based on the values of a model and its related models.

    Args:
        model (Any): The main model for which the hash is being built.
        field_names (Optional[List[str]]): The names of the fields to include in the hash calculation.
                                            If not provided, all fields will be included. Defaults to None.
        pk (Optional[UUID]): The primary key of the main model in case of need a hash for one instance.
        filter_opts (Optional[Dict[str, Any]]): Optional filter options to apply to the queryset.

    Attributes:
        queryset (QuerySet): The queryset representing the main model.
        values_string (str): A string representation of the values in the queryset.
        main_model (Any): The main model for which the hash is being built.
        related_string (str): A string representation of the related models' values.

    Methods:
        build: Builds and returns the hash string.
        set_m2m_related_model_string: Sets the related_string attribute based on a ManyToMany relation.
        set_related_model_string: Sets the related_string attribute based on a ForeignKey or OneToOne relation.

    Private Methods:
        _process_queryset: Processes the queryset by applying filters and selecting specific fields.

    """

    def __init__(
        self,
        model: Any,
        field_names: Optional[List[str]] = None,
        pk: Optional[UUID] = None,
        filter_opts: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initializes a new instance of the HashByModelBuilder class.

        Args:
            model (Any): The main model for which the hash is being built.
            field_names (Optional[List[str]]): The names of the fields to include in the hash calculation.
                                            If not provided, all fields will be included. Defaults to None.
            pk (Optional[UUID], optional): The primary key of the main model in case of need a hash for one instance.
                                           Defaults to None.
            filter_opts (Optional[Dict[str, Any]], optional): Optional filter options to apply to the queryset.
                                                              Defaults to None.

        """
        self.main_model = model
        self.related_string = ""
        if pk:
            self.queryset = model.objects.filter(pk=pk)
        else:
            self.queryset = model.objects.all()
        qs = self._process_queryset(queryset=self.queryset, field_names=field_names, filter_opts=filter_opts)
        self.values_string = str(list(qs))

    def build(self) -> str:
        """
        Builds and returns the hash string.

        Returns:
            str: The hash string.

        """
        string_to_be_hashed = self.values_string
        if self.related_string:
            string_to_be_hashed += self.related_string
        return hashlib.md5(string_to_be_hashed.encode("utf-8")).hexdigest()

    def set_m2m_related_model_string(
        self,
        relation_name: str,
        field_names: Optional[List[str]] = None,
        filter_opts: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Sets the related_string attribute based on a ManyToMany relation.

        Args:
            relation_name (str): The name of the ManyToMany relation.
            field_names (Optional[List[str]]): The names of the fields to include in the hash calculation.
                                            If not provided, all fields will be included. Defaults to None.
            filter_opts (Optional[Dict[str, Any]], optional): Optional filter options to apply to the related model's
                                                            queryset. Defaults to None.

        """
        for obj in self.queryset:
            related_model = getattr(obj, relation_name)

            if related_model.exists():
                queryset = self._process_queryset(
                    queryset=related_model.all(), field_names=field_names, filter_opts=filter_opts
                )
                self.related_string += str(list(queryset))

    def set_related_model_string(self, relation_name: str, field_names: Optional[List[str]] = None) -> None:
        """
        Sets the related_string attribute based on a ForeignKey or OneToOne relation.

        Args:
            relation_name (str): The name of the ForeignKey or OneToOne relation.
            field_names (Optional[List[str]]): The names of the fields to include in the hash calculation.
                                            If not provided, all fields will be included. Defaults to None.

        """
        related_model = getattr(self.main_model, relation_name)
        queryset = self._process_queryset(queryset=related_model.all(), field_names=field_names)
        self.related_string += str(queryset)

    def _process_queryset(
        self, queryset: QuerySet, filter_opts: Optional[Dict[str, Any]], field_names: Optional[List[str]] = None
    ) -> QuerySet:
        """
        Processes the queryset by applying filters and selecting specific fields.

        Args:
            queryset (QuerySet): The queryset to process.
            field_names (Optional[List[str]]): The names of the fields to include in the hash calculation.
                                            If not provided, all fields will be included. Defaults to None.
            filter_opts (Optional[Dict[str, Any]], optional): Optional filter options to apply to the queryset.
                                                              Defaults to None.

        Returns:
            QuerySet: The processed queryset.

        """
        if filter_opts:
            queryset = queryset.filter(**filter_opts)

        queryset = queryset.values() if not field_names else queryset.values(*field_names)
        return queryset
