# Customer Management Actions Implementation

## Overview
This document describes the implementation of action buttons in the `/customers/` page for managing customer accounts.

## Implemented Actions

### 1. View Customer
- **Endpoint**: `GET /customers/details/<customer_id>/`
- **Permission**: Admin/Support
- **Functionality**: Displays customer details in a modal including basic info and KYC data

### 2. Edit Customer
- **Endpoint**: `POST /customers/edit/`
- **Permission**: Admin/Support
- **Functionality**: Opens a modal form to edit customer name, email, and phone
- **Payload**:
  ```json
  {
    "customer_id": 123,
    "full_name": "Updated Name",
    "email": "new@example.com",
    "phone": "+1234567890"
  }
  ```

### 3. Toggle Status (Activate/Deactivate)
- **Endpoint**: `POST /customers/toggle_status/`
- **Permission**: Admin/Support
- **Functionality**: Toggles customer active status
- **Payload**:
  ```json
  {
    "customer_id": 123,
    "action": "activate" | "deactivate"
  }
  ```

### 4. Reset Password
- **Endpoint**: `POST /customers/reset_password/`
- **Permission**: Admin/Support
- **Functionality**: Generates new random password and updates user
- **Note**: Email sending not yet implemented (TODO)
- **Payload**:
  ```json
  {
    "customer_id": 123
  }
  ```

### 5. Delete Customer (Soft Delete)
- **Endpoint**: `POST /customers/delete/`
- **Permission**: Admin/Support
- **Functionality**: Deactivates customer if no unpaid invoices
- **Constraints**: Fails if customer has unpaid invoices (AccountEntry with entry_type="invoice" and amount_usd > 0)
- **Payload**:
  ```json
  {
    "customer_id": 123
  }
  ```

### 6. Purge Data (Hard Delete)
- **Endpoint**: `POST /customers/purge/`
- **Permission**: Admin only
- **Functionality**: Permanently deletes customer and all associated data
- **Security**: Requires admin password confirmation
- **Payload**:
  ```json
  {
    "customer_id": 123,
    "admin_password": "password"
  }
  ```

## Business Rules
- **Unpaid Invoices Check**: Delete action checks for any invoice entries with positive amounts in the customer's billing account
- **Permissions**:
  - View/Edit/Toggle/Reset/Delete: Admin or Support roles
  - Purge: Admin role only, with password verification
- **Data Integrity**: Soft delete preserves data for audit; hard delete removes everything

## Frontend Implementation
- All actions use AJAX POST requests with JSON payloads
- CSRF tokens included for security
- Table reloads after successful operations
- User confirmations for destructive actions
- Modal for editing with form validation

## Security Considerations
- All endpoints require authentication and role-based access
- JSON parsing with error handling
- Password verification for purge operations
- Input validation and sanitization

## TODOs
- Implement email sending for password reset
- Add more comprehensive input validation
- Consider adding audit logging for all actions
- Implement undo functionality for soft delete

## Testing
TDD tests implemented in `customers/tests.py` covering:
- Successful operations
- Permission checks
- Business rule enforcement
- Error handling