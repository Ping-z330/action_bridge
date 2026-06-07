from dataclasses import dataclass
from typing import Any, Callable

# 飞书发送能力的接口包装类，定义了发送各种类型消息到飞书的函数类型

# 导入具体的发送函数，这些函数实现了向飞书发送不同类型消息的逻辑，比如发送任务详情、发送项目进展总结等
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


# 定义一个不可变的数据类 FeishuDeliveryPort，包含多个发送消息的函数，这些函数都是 Callable 类型，接受任意参数并返回任意结果
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


# 提供一个函数来获取默认的 FeishuDeliveryPort 实例，这个实例将所有发送函数都绑定到对应的实现上，方便在处理飞书事件时使用这个接口来发送消息
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
