from dataclasses import dataclass
from typing import Any, Callable

from app.services.feishu_service import (
    send_action_item_completed_notice,
    send_help_card,
    send_memory_deleted_notice,
    send_memory_list_summary,
    send_memory_saved_notice,
    send_open_tasks_summary,
    send_pending_action_notice,
    send_project_progress_summary,
    send_task_create_clarification,
    send_task_create_confirmation,
    send_task_deadline_update_confirmation,
    send_task_detail_summary,
    send_task_not_found_notice,
    send_task_owner_update_confirmation,
)


@dataclass(frozen=True)
class FeishuDeliveryPort:
    send_action_item_completed_notice: Callable[..., Any]
    send_help_card: Callable[..., Any]
    send_memory_deleted_notice: Callable[..., Any]
    send_memory_list_summary: Callable[..., Any]
    send_memory_saved_notice: Callable[..., Any]
    send_open_tasks_summary: Callable[..., Any]
    send_pending_action_notice: Callable[..., Any]
    send_project_progress_summary: Callable[..., Any]
    send_task_create_clarification: Callable[..., Any]
    send_task_create_confirmation: Callable[..., Any]
    send_task_deadline_update_confirmation: Callable[..., Any]
    send_task_detail_summary: Callable[..., Any]
    send_task_not_found_notice: Callable[..., Any]
    send_task_owner_update_confirmation: Callable[..., Any]


def get_default_feishu_delivery() -> FeishuDeliveryPort:
    return FeishuDeliveryPort(
        send_action_item_completed_notice=send_action_item_completed_notice,
        send_help_card=send_help_card,
        send_memory_deleted_notice=send_memory_deleted_notice,
        send_memory_list_summary=send_memory_list_summary,
        send_memory_saved_notice=send_memory_saved_notice,
        send_open_tasks_summary=send_open_tasks_summary,
        send_pending_action_notice=send_pending_action_notice,
        send_project_progress_summary=send_project_progress_summary,
        send_task_create_clarification=send_task_create_clarification,
        send_task_create_confirmation=send_task_create_confirmation,
        send_task_deadline_update_confirmation=send_task_deadline_update_confirmation,
        send_task_detail_summary=send_task_detail_summary,
        send_task_not_found_notice=send_task_not_found_notice,
        send_task_owner_update_confirmation=send_task_owner_update_confirmation,
    )
