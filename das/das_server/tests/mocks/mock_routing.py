# from activity.models import Event
#
# from django.dispatch import receiver
# from django.db.models.signals import post_save
#
# # import das_server.tasks as tasks
# import time
#
#
# receiver_enabled = False
#
#
# def enable_receiver():
#     global receiver_enabled
#     receiver_enabled = True
#
#
# def disable_receiver():
#     global receiver_enabled
#     receiver_enabled = False
#
#
# @receiver(post_save, sender=Event)
# def mock_event_post_save(sender, instance, created, **kwargs):
#     global receiver_enabled
#     if receiver_enabled:
#         print("---MOCK EVENT POST SAVE---")
#         # tasks.queue_event_alert(str(instance.pk))
#
#
# pending_calls_to_check_event_activity = []
#
#
# def mock_send_task(name, args=None, kwargs=None, countdown=None,
#                    eta=None, task_id=None, producer=None, connection=None,
#                    router=None, result_cls=None, expires=None,
#                    publisher=None, link=None, link_error=None,
#                    add_to_parent=True, group_id=None, retries=0, chord=None,
#                    reply_to=None, time_limit=None, soft_time_limit=None,
#                    root_id=None, parent_id=None, route_name=None,
#                    shadow=None, chain=None, task_type=None, **options):
#     print(name)
#     if name == 'das_server.tasks.check_event_activity':
#         global pending_calls_to_check_event_activity
#         pending_calls_to_check_event_activity.append((args[0], args[1]))
#     # elif name == 'das_server.tasks.queue_alert_for_all_users':
#     #     tasks.queue_alert_for_all_users(args[0], args[1])
#     # elif name == 'das_server.tasks.send_alert_to_specific_user':
#     #     tasks.send_alert_to_specific_user(args[0], args[1], args[2])
#
#
# def simulate_five_second_wait():
#     global pending_calls_to_check_event_activity
#     time.sleep(2)
#     # for args in pending_calls_to_check_event_activity:
#     #     tasks.check_event_activity(args[0], args[1])
#     pending_calls_to_check_event_activity = []
