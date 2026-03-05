from rest_framework import status
from rest_framework.response import Response


def success_response(data=None, message: str = "success", code: int = 200, status_code: int = status.HTTP_200_OK):
    return Response({"code": code, "message": message, "data": data}, status=status_code)


def error_response(message: str = "error", code: int = 400, data=None, status_code: int = status.HTTP_400_BAD_REQUEST):
    return Response({"code": code, "message": message, "data": data}, status=status_code)
