from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "code": 200,
                "message": "success",
                "data": {
                    "count": self.page.paginator.count,
                    "page": self.page.number,
                    "page_size": self.get_page_size(self.request),
                    "num_pages": self.page.paginator.num_pages,
                    "results": data,
                },
            }
        )
