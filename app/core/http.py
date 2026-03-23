import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from app.core.config import Settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def build_request_headers(
    settings: Settings, headers: Mapping[str, str] | None = None
) -> dict[str, str]:
    merged: dict[str, str] = {}
    if settings.parser_user_agent:
        merged["User-Agent"] = settings.parser_user_agent
    if headers:
        merged.update(headers)
    return merged


def compute_backoff_seconds(base_seconds: float, attempt: int) -> float:
    return base_seconds * (2 ** max(0, attempt - 1))


def safe_response_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_retry_after_seconds(response: Any) -> float | None:
    payload = safe_response_json(response)
    retry_after = payload.get("parameters", {}).get("retry_after")
    if retry_after is not None:
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            return None

    headers = getattr(response, "headers", {}) or {}
    header_retry = headers.get("Retry-After")
    if header_retry is not None:
        try:
            return float(header_retry)
        except (TypeError, ValueError):
            return None
    return None


def request_with_retry(
    *,
    request_callable: Callable[..., Any],
    logger: logging.Logger,
    service_name: str,
    method: str,
    url: str,
    timeout: int | float,
    retry_attempts: int,
    retry_base_seconds: float,
    headers: Mapping[str, str] | None = None,
    retryable_status_codes: set[int] | None = None,
    **request_kwargs: Any,
) -> Any:
    retryable_codes = retryable_status_codes or RETRYABLE_STATUS_CODES
    attempts = max(1, retry_attempts)
    call_kwargs = dict(request_kwargs)
    call_kwargs["timeout"] = timeout
    if headers:
        call_kwargs["headers"] = dict(headers)

    for attempt in range(1, attempts + 1):
        try:
            response = request_callable(url, **call_kwargs)
        except Exception as exc:
            if attempt >= attempts:
                logger.exception(
                    "%s HTTP request failed after %s attempt(s): %s %s",
                    service_name,
                    attempts,
                    method,
                    url,
                )
                raise

            sleep_seconds = compute_backoff_seconds(retry_base_seconds, attempt)
            logger.warning(
                "%s HTTP request error on attempt %s/%s for %s %s: %s; retrying in %.2fs",
                service_name,
                attempt,
                attempts,
                method,
                url,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            continue

        status_code = getattr(response, "status_code", None)
        if status_code in retryable_codes and attempt < attempts:
            sleep_seconds = extract_retry_after_seconds(response) or compute_backoff_seconds(
                retry_base_seconds, attempt
            )
            logger.warning(
                "%s HTTP status %s on attempt %s/%s for %s %s; retrying in %.2fs",
                service_name,
                status_code,
                attempt,
                attempts,
                method,
                url,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            continue

        if status_code is not None and status_code >= 400:
            logger.error(
                "%s HTTP request returned status %s for %s %s",
                service_name,
                status_code,
                method,
                url,
            )
        return response

    raise RuntimeError(f"{service_name} request loop exited unexpectedly for {method} {url}")
