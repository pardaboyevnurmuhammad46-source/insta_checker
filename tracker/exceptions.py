from .instagram_errors import InstagramErrorType


class InstagramBaseError(Exception):
    pass


class InstagramNetworkError(InstagramBaseError):
    pass


class InstagramOAuthError(InstagramBaseError):
    pass


class InstagramOAuthNetworkError(InstagramOAuthError, InstagramNetworkError):
    pass


class InstagramPublishError(InstagramBaseError):
    pass


class InstagramPublishNetworkError(InstagramPublishError, InstagramNetworkError):
    pass


class InstagramMetricsError(InstagramBaseError):
    def __init__(
        self,
        message: str,
        is_deleted: bool = False,
        is_auth_error: bool = False,
        error_type: InstagramErrorType = InstagramErrorType.OTHER,
        status_code: int | None = None,
        error_code: int | None = None,
        error_subcode: int | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.is_deleted = is_deleted or (error_type == InstagramErrorType.MEDIA_NOT_FOUND)
        self.is_auth_error = is_auth_error or (error_type == InstagramErrorType.TOKEN_INVALID)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode


class InstagramRateLimitError(InstagramMetricsError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('error_type', InstagramErrorType.RATE_LIMIT)
        super().__init__(message, **kwargs)


class InstagramMetricsNetworkError(InstagramMetricsError, InstagramNetworkError):
    pass


class TokenInvalid(InstagramMetricsError):
    """
    Instagram access token yaroqsiz, muddati o'tgan yoki bekor qilingan (xato kodi 190).
    """
    def __init__(
        self,
        message: str = "Instagram access token yaroqsiz yoki muddati o'tgan (xato kodi 190)",
        error_code: int = 190,
        error_subcode: int | None = None,
        status_code: int | None = 400,
        **kwargs,
    ):
        super().__init__(
            message=message,
            is_auth_error=True,
            error_type=InstagramErrorType.TOKEN_INVALID,
            status_code=status_code,
            error_code=error_code,
            error_subcode=error_subcode,
        )
        self.extra = kwargs


class MetaWebhookError(Exception):
    pass
