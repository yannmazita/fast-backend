# API Specifications & Schemas

This document details the complete REST API interface of `fast-backend`, specifying endpoints, query parameters, request-response schemas (Pydantic models), and standardized error responses.

---

## 🍪 Authentication Endpoints

Registered on prefix `/` (with additional `/oauth` sub-routes). Supports credentials login, token rotation, and safe cookie-based de-authentications.

### 1. Account Login
*   **Path:** `POST /login`
*   **Request Schema (`UserLogin`):**
    ```json
    {
      "username": "johndoe",
      "password": "securepassword123"
    }
    ```
*   **Response Schema (`Token`):**
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "expires_at": "2026-06-11T12:00:00Z"
    }
    ```
*   **Behavior:** Sets secure `access_token` and `refresh_token` as **HttpOnly, Secure, SameSite=Lax** cookies in addition to returning the access token in the response payload.

---

### 2. Token Refresh Rotation
*   **Path:** `POST /refresh`
*   **Request:** Binds active `refresh_token` cookie from the incoming request headers.
*   **Response Schema (`Token`):** Returns rotated `access_token` and updates client cookies.

---

### 3. Account Logout
*   **Path:** `POST /logout`
*   **Status Code:** `204 No Content`
*   **Behavior:** Locates active `refresh_token` JTI in the DB, marks it as **revoked**, and clears all authorization cookies from the client browser.

---

## 🌐 OAuth2 Integration (Google & Apple)

Enables third-party registrations and zero-password authentication.

### 1. Initiate Google Login
*   **Path:** `GET /oauth/google/login`
*   **Query Parameters:** `redirect_uri` (string)
*   **Behavior:** Redirects user's browser to Google's official authorization portal with state validation parameters.

---

### 2. Google OAuth Callback
*   **Path:** `GET /oauth/google/callback`
*   **Query Parameters:** `code` (string), `state` (string)
*   **Success Response (User Registered):** Sets HttpOnly JWT cookies and authenticates the user immediately.
*   **Pending Response (New Username Required):**
    *   **Status Code:** `200 OK`
    *   **Body Content (`OAuthAuthenticationResult`):**
        ```json
        {
          "status": "USERNAME_REGISTRATION_REQUIRED",
          "pending_registration_token": "eyJhbGciOi...",
          "user": null
        }
        ```

---

### 3. Complete OAuth Registration
*   **Path:** `POST /oauth/complete-registration`
*   **Request Schema (`CompleteOAuthRegistrationRequest`):**
    ```json
    {
      "pending_token": "eyJhbGciOi...",
      "username": "custom_username_1"
    }
    ```
*   **Response Schema (`Token`):** Returns active access tokens and issues standard HttpOnly cookies upon successful username allocation.

---

## 👤 User & Profile Endpoints

All endpoints below require a valid active JWT (extracted from Bearer headers or cookies) containing the appropriate permission scope.

### 1. Read Current Profile
*   **Path:** `GET /me`
*   **Required Scope:** `::PROFILE::READ_SELF::`
*   **Response Schema (`UserRead`):**
    ```json
    {
      "id": "e0bfa9c3-7dd0-482c-8067-ff2b6f194e1e",
      "username": "johndoe",
      "email": "john@example.com",
      "roles": "REGULAR",
      "is_active": true,
      "is_guest": false,
      "disabled_at": null,
      "created_at": "2026-06-11T10:00:00Z",
      "updated_at": "2026-06-11T10:00:00Z"
    }
    ```

---

### 2. Update Current Profile
*   **Path:** `PATCH /me`
*   **Required Scope:** `::PROFILE::UPDATE_SELF::`
*   **Request Schema (`UserUpdate`):**
    ```json
    {
      "email": "newjohn@example.com"
    }
    ```
*   **Response Schema (`UserRead`)**

---

### 3. Disable Own Account
*   **Path:** `POST /me/disable`
*   **Required Scope:** `::PROFILE::DISABLE_SELF::`
*   **Status Code:** `200 OK`
*   **Response Schema (`UserRead`):** Returns deactivated user account representation. Sets `is_active` to `false` and captures `disabled_at` timestamp.

---

### 4. Delete Own Account
*   **Path:** `DELETE /me`
*   **Required Scope:** `::PROFILE::DELETE_SELF::`
*   **Response Schema (`UserRead`):** Returns representation of deleted user account. Removes record from DB.

---

## 🛡️ Administrative & Ban Endpoints

Requires administrative scope credentials.

### 1. List All Users
*   **Path:** `GET /` (on user prefix)
*   **Required Scope:** `::USERS::LIST::`
*   **Query Parameters:** `offset` (default: 0), `limit` (default: 50)
*   **Response Schema (`Users`):**
    ```json
    {
      "users": [ ... ],
      "total": 125
    }
    ```

---

### 2. Issue Ban Against User
*   **Path:** `POST /` (on user prefix)
*   **Required Scope:** `::BANS::CREATE::`
*   **Request Schema (`BanCreate`):**
    ```json
    {
      "user_id": "e0bfa9c3-7dd0-482c-8067-ff2b6f194e1e",
      "reason": "Repeated violations of terms of service.",
      "expires_at": "2026-07-11T10:00:00Z"
    }
    ```
*   **Response Schema (`BanRead`)**

---

### 3. Fetch User Ban History
*   **Path:** `GET /{user_id}/bans`
*   **Required Scope:** `::BANS::READ_HISTORY_ANY::`
*   **Response Schema:** `tuple[list[BanRead], int]` (returns ban historical list along with count).

---

### 4. Lift/Deactivate User Ban
*   **Path:** `PATCH /bans/{ban_id}/deactivate`
*   **Required Scope:** `::BANS::DEACTIVATE::`
*   **Response Schema (`BanRead`):** Returns modified ban record indicating `is_currently_active=false` and captures deactivator admin user ID.

---

## 🚨 Error Handling Code Maps

Uncaught server faults or custom domain exceptions trigger a standardized JSON response error payload in `src/main.py`.

### Standard Error Schema
```json
{
  "detail": "Descriptive message explaining the exception details.",
  "error_code": "STANDARD_ERROR_TAG"
}
```

### Application Error Codes Mapping

| Class Exception | HTTP Status | `error_code` Value | Description |
| :--- | :--- | :--- | :--- |
| `InvalidCredentials` | `401 Unauthorized` | `INVALID_CREDENTIALS` | Invalid username or password entry. |
| `PermissionDenied` | `403 Forbidden` | `PERMISSION_DENIED` | Missing required scope permissions. |
| `UserBannedError` | `403 Forbidden` | `USER_BANNED` | Account has an active ban record. |
| `UserDisabledError` | `403 Forbidden` | `USER_DISABLED` | Account has been deactivated. |
| `ResourceNotFound` | `404 Not Found` | `RESOURCE_NOT_FOUND` | DB query returned no records. |
| `DuplicateResource` | `409 Conflict` | `DUPLICATE_RESOURCE` | Violates unique constraints (e.g. username). |
| `BadRequestError` | `400 Bad Request` | `BAD_REQUEST` | Malformed inputs or mismatch validations. |
| `SQLAlchemyError` | `500 Server Error`| *(None)* | Safely masked as database transactional error. |
