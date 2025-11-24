# import json
# import logging
# from decimal import Decimal, InvalidOperation
# Ce fichier a été fusionné dans views.py et peut être supprimé.
# from django.contrib.auth.decorators import login_required, user_passes_test
# from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_protect
# from django.views.decorators.http import require_POST

# from site_survey.models import ExtraCharge

# # Set up logger for this module
# logger = logging.getLogger(__name__)


# @login_required(login_url="login_page")
# @user_passes_test(lambda u: u.is_staff, login_url="login_page")
# def get_extra_charges(request):
#     """Get paginated list of extra charges"""
#     if request.headers.get("x-requested-with") != "XMLHttpRequest":
#         return JsonResponse({"error": "Invalid request"}, status=400)

#     extra_charges = ExtraCharge.objects.all().order_by(
#         "cost_type", "display_order", "item_name"
#     )
#     paginator = Paginator(extra_charges, 10)  # Show 10 items per page

#     page_number = request.GET.get("page", 1)
#     try:
#         items_page = paginator.page(page_number)
#     except PageNotAnInteger:
#         items_page = paginator.page(1)
#     except EmptyPage:
#         items_page = paginator.page(paginator.num_pages)

#     data = []
#     for item in items_page:
#         data.append(
#             {
#                 "id": item.id,
#                 "cost_type": item.cost_type,
#                 "cost_type_display": item.get_cost_type_display(),
#                 "item_name": item.item_name,
#                 "description": item.description,
#                 "brand": item.brand,
#                 "model": item.model,
#                 "unit_price": str(item.unit_price),
#                 "is_active": item.is_active,
#                 "display_order": item.display_order,
#                 "specifications": item.specifications,
#             }
#         )

#     return JsonResponse(
#         {
#             "extra_charges": data,
#             "pagination": {
#                 "has_next": items_page.has_next(),
#                 "has_previous": items_page.has_previous(),
#                 "page_number": items_page.number,
#                 "total_pages": paginator.num_pages,
#                 "total_items": paginator.count,
#             },
#         }
#     )


# @login_required(login_url="login_page")
# @user_passes_test(lambda u: u.is_staff, login_url="login_page")
# @require_POST
# @csrf_protect
# def create_extra_charge(request):
#     """Create a new extra charge"""
#     logger.info(
#         f"create_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
#     )

#     if not request.headers.get("x-requested-with") == "XMLHttpRequest":
#         logger.warning(
#             "create_extra_charge: Invalid request type - not an AJAX request"
#         )
#         return JsonResponse(
#             {"success": False, "message": "Invalid request type."}, status=400
#         )

#     try:
#         data = json.loads(request.body)
#         logger.info(f"create_extra_charge: Received data: {data}")

#         # Extract data from request
#         cost_type = data.get("cost_type")
#         item_name = data.get("item_name")
#         description = data.get("description", "")
#         brand = data.get("brand", "")
#         model = data.get("model", "")
#         unit_price = data.get("unit_price")
#         is_active = data.get("is_active", True)
#         display_order = data.get("display_order", 0)
#         specifications = data.get("specifications", "")

#         # Validate required fields
#         if not all([cost_type, item_name, unit_price]):
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "message": "Cost type, item name, and unit price are required.",
#                 },
#                 status=400,
#             )

#         # Validate unit price
#         try:
#             unit_price = Decimal(str(unit_price))
#             if unit_price < 0:
#                 return JsonResponse(
#                     {"success": False, "message": "Unit price must be positive."},
#                     status=400,
#                 )
#         except (ValueError, InvalidOperation):
#             return JsonResponse(
#                 {"success": False, "message": "Invalid unit price format."}, status=400
#             )

#         # Check for duplicate item names
#         if ExtraCharge.objects.filter(item_name=item_name).exists():
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "message": "An extra charge with this item name already exists.",
#                 },
#                 status=400,
#             )

#         # Create the extra charge
#         extra_charge = ExtraCharge.objects.create(
#             cost_type=cost_type,
#             item_name=item_name,
#             description=description,
#             brand=brand,
#             model=model,
#             unit_price=unit_price,
#             is_active=bool(is_active),
#             display_order=int(display_order),
#             specifications=specifications,
#         )

#         logger.info(f"create_extra_charge: Created item with ID {extra_charge.id}")

#         return JsonResponse(
#             {
#                 "success": True,
#                 "message": f"Extra charge '{item_name}' created successfully.",
#                 "extra_charge": {
#                     "id": extra_charge.id,
#                     "cost_type": extra_charge.cost_type,
#                     "cost_type_display": extra_charge.get_cost_type_display(),
#                     "item_name": extra_charge.item_name,
#                     "description": extra_charge.description,
#                     "brand": extra_charge.brand,
#                     "model": extra_charge.model,
#                     "unit_price": str(extra_charge.unit_price),
#                     "is_active": extra_charge.is_active,
#                     "display_order": extra_charge.display_order,
#                     "specifications": extra_charge.specifications,
#                 },
#             }
#         )

#     except json.JSONDecodeError:
#         logger.error("create_extra_charge: Invalid JSON data")
#         return JsonResponse(
#             {"success": False, "message": "Invalid JSON data."}, status=400
#         )
#     except Exception as e:
#         logger.error(f"create_extra_charge: Unexpected error: {str(e)}")
#         return JsonResponse({"success": False, "message": str(e)}, status=500)


# @login_required(login_url="login_page")
# @user_passes_test(lambda u: u.is_staff, login_url="login_page")
# @require_POST
# @csrf_protect
# def update_extra_charge(request):
#     """Update an existing extra charge"""
#     logger.info(
#         f"update_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
#     )

#     if not request.headers.get("x-requested-with") == "XMLHttpRequest":
#         logger.warning(
#             "update_extra_charge: Invalid request type - not an AJAX request"
#         )
#         return JsonResponse(
#             {"success": False, "message": "Invalid request type."}, status=400
#         )

#     try:
#         data = json.loads(request.body)
#         logger.info(f"update_extra_charge: Received data: {data}")

#         # Extract data from request
#         extracharge_id = data.get("extracharge_id")
#         cost_type = data.get("cost_type")
#         item_name = data.get("item_name")
#         description = data.get("description", "")
#         brand = data.get("brand", "")
#         model = data.get("model", "")
#         unit_price = data.get("unit_price")
#         is_active = data.get("is_active", True)
#         display_order = data.get("display_order", 0)
#         specifications = data.get("specifications", "")

#         # Validate required fields
#         if not all([extracharge_id, cost_type, item_name, unit_price]):
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "message": "ID, cost type, item name, and unit price are required.",
#                 },
#                 status=400,
#             )

#         # Get the extra charge
#         try:
#             extra_charge = ExtraCharge.objects.get(id=extracharge_id)
#         except ExtraCharge.DoesNotExist:
#             return JsonResponse(
#                 {"success": False, "message": "Extra charge not found."}, status=404
#             )

#         # Validate unit price
#         try:
#             unit_price = Decimal(str(unit_price))
#             if unit_price < 0:
#                 return JsonResponse(
#                     {"success": False, "message": "Unit price must be positive."},
#                     status=400,
#                 )
#         except (ValueError, InvalidOperation):
#             return JsonResponse(
#                 {"success": False, "message": "Invalid unit price format."}, status=400
#             )

#         # Check for duplicate item names (excluding current item)
#         if (
#             ExtraCharge.objects.filter(item_name=item_name)
#             .exclude(id=extracharge_id)
#             .exists()
#         ):
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "message": "An extra charge with this item name already exists.",
#                 },
#                 status=400,
#             )

#         # Update the extra charge
#         extra_charge.cost_type = cost_type
#         extra_charge.item_name = item_name
#         extra_charge.description = description
#         extra_charge.brand = brand
#         extra_charge.model = model
#         extra_charge.unit_price = unit_price
#         extra_charge.is_active = bool(is_active)
#         extra_charge.display_order = int(display_order)
#         extra_charge.specifications = specifications
#         extra_charge.save()

#         logger.info(f"update_extra_charge: Updated item with ID {extra_charge.id}")

#         return JsonResponse(
#             {
#                 "success": True,
#                 "message": f"Extra charge '{item_name}' updated successfully.",
#                 "extra_charge": {
#                     "id": extra_charge.id,
#                     "cost_type": extra_charge.cost_type,
#                     "cost_type_display": extra_charge.get_cost_type_display(),
#                     "item_name": extra_charge.item_name,
#                     "description": extra_charge.description,
#                     "brand": extra_charge.brand,
#                     "model": extra_charge.model,
#                     "unit_price": str(extra_charge.unit_price),
#                     "is_active": extra_charge.is_active,
#                     "display_order": extra_charge.display_order,
#                     "specifications": extra_charge.specifications,
#                 },
#             }
#         )

#     except json.JSONDecodeError:
#         logger.error("update_extra_charge: Invalid JSON data")
#         return JsonResponse(
#             {"success": False, "message": "Invalid JSON data."}, status=400
#         )
#     except Exception as e:
#         logger.error(f"update_extra_charge: Unexpected error: {str(e)}")
#         return JsonResponse({"success": False, "message": str(e)}, status=500)


# @login_required(login_url="login_page")
# @user_passes_test(lambda u: u.is_staff, login_url="login_page")
# @require_POST
# @csrf_protect
# def delete_extra_charge(request):
#     """Delete an extra charge"""
#     logger.info(
#         f"delete_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
#     )

#     if not request.headers.get("x-requested-with") == "XMLHttpRequest":
#         logger.warning(
#             "delete_extra_charge: Invalid request type - not an AJAX request"
#         )
#         return JsonResponse(
#             {"success": False, "message": "Invalid request type."}, status=400
#         )

#     try:
#         data = json.loads(request.body)
#         extracharge_id = data.get("extracharge_id")

#         if not extracharge_id:
#             return JsonResponse(
#                 {"success": False, "message": "Extra charge ID is required."},
#                 status=400,
#             )

#         # Get and delete the extra charge
#         try:
#             extra_charge = ExtraCharge.objects.get(id=extracharge_id)

#             # Check if this extra charge is used in any survey additional costs
#             if (
#                 hasattr(extra_charge, "surveyadditionalcost_set")
#                 and extra_charge.surveyadditionalcost_set.exists()
#             ):
#                 return JsonResponse(
#                     {
#                         "success": False,
#                         "message": "Cannot delete this extra charge as it is being used in existing site surveys.",
#                     },
#                     status=400,
#                 )

#             item_name = extra_charge.item_name
#             extra_charge.delete()

#             logger.info(f"delete_extra_charge: Deleted item with ID {extracharge_id}")

#             return JsonResponse(
#                 {
#                     "success": True,
#                     "message": f"Extra charge '{item_name}' deleted successfully.",
#                 }
#             )

#         except ExtraCharge.DoesNotExist:
#             return JsonResponse(
#                 {"success": False, "message": "Extra charge not found."}, status=404
#             )

#     except json.JSONDecodeError:
#         logger.error("delete_extra_charge: Invalid JSON data")
#         return JsonResponse(
#             {"success": False, "message": "Invalid JSON data."}, status=400
#         )
#     except Exception as e:
#         logger.error(f"delete_extra_charge: Unexpected error: {str(e)}")
#         return JsonResponse({"success": False, "message": str(e)}, status=500)
