# Security, RBAC, and OAuth Flows

This document details the security model, token rotation lifecycle, Role-Based Access Control (RBAC), and external OAuth identity federation workflows in `fast-backend`.

---

## 🛡️ Role-Based Access Control (RBAC)

To provide granular security controls, the system decouples user **Roles** from specific **Permission Scopes**. Users are assigned coarse roles, which are dynamically resolved at runtime into highly specific permission scopes.

### 1. Abstract User Roles (`src/features/auth/utils/scopes.py`)
Six abstract user roles are defined via the `UserRoles` string enum:
*   `GUEST`: Temporary, low-clearance anonymous users.
*   `REGULAR`: Standard registered accounts.
*   `PREMIUM`: Accounts containing premium features clearance.
*   `MODERATOR`: Accounts containing standard community moderator actions.
*   `CONTENT_ADMIN`: Specialized moderators focused on item/content curation.
*   `ADMINISTRATOR`: High-clearance roles. Granted all scopes globally.

---

### 2. Granular Permission Scopes Mapping
Scopes represent exact, transaction-specific permissions. They are defined as structured string keys:

```python
OAUTH_SCOPES = {
    # Profile Scopes
    "::PROFILE::READ_SELF::": "Read own user profile.",
    "::PROFILE::UPDATE_SELF::": "Update own user profile.",
    "::PROFILE::DELETE_SELF::": "Delete own user account.",
    "::PROFILE::DISABLE_SELF::": "Disable own user account.",
    
    # User Management Scopes (Admins / Moderators)
    "::USERS::CREATE::": "Create new user accounts.",
    "::USERS::LIST::": "List all user accounts.",
    "::USERS::READ_ANY::": "Read any user's profile.",
    "::USERS::UPDATE_ANY::": "Update any user's profile (like roles, active status).",
    "::USERS::DELETE_ANY::": "Delete any user's account.",
    
    # Ban Management Scopes
    "::BANS::CREATE::": "Create bans for users.",
    "::BANS::READ_HISTORY_ANY::": "Read ban history for any user.",
    "::BANS::DEACTIVATE::": "Deactivate user bans.",
    
    # WebSocket Scope
    "::WEBSOCKETS::CONNECT::": "Connect to WebSocket for real-time features.",
    
    # User Data Export Scope
    "::USER_DATA::EXPORT_SELF::": "Export own user data."
}
```

#### Roles to Scopes Mapping Configuration
The scopes are aggregated using helper utilities (`get_scopes_for_role_strings`):
*   `GUEST_USER_SCOPES` $\rightarrow$ `READ_SELF`, `WEBSOCKETS::CONNECT`, `EXPORT_SELF`.
*   `REGULAR_USER_SCOPES` $\rightarrow$ Guest scopes + `UPDATE_SELF`, `DELETE_SELF`, `DISABLE_SELF`.
*   `PREMIUM_USER_SCOPES` $\rightarrow$ Regular scopes + `SOME_PREMIUM_FEATURE::SOME_ACTION`.
*   `MODERATOR_SCOPES` $\rightarrow$ Regular scopes + `USERS::LIST`, `USERS::READ_ANY`, and all `BANS` management scopes.
*   `ADMINISTRATOR_SCOPES` $\rightarrow$ Automatically aggregates 100% of defined scopes (`ALL_DEFINED_SCOPES`).

---

## 🔑 JWT Lifecycle & Token Rotation

The system implements statelessly verified **JWT Access Tokens** for requests, combined with statefully tracked **JWT Refresh Tokens** in the database to support secure token rotation.

```text
  Client                                     API Gateway / Backend
    │                                                  │
    ├───────── 1. POST /login ────────────────────────>│ (Argon2 Verify)
    │                                                  │
    │<──────── 2. Set Cookie (HttpOnly Access/Refresh) ┤ (Record JTI in DB)
    │                                                  │
    │                                                  │
    ├───────── 3. GET /me (With Cookie/Bearer) ───────>│ (Verify Signature & Scopes)
    │                                                  │
    │                                                  │
    ├───────── 4. POST /refresh (Rotate Token) ───────>│ (Checks JTI active in DB)
    │                                                  │ (Revokes old JTI, Creates new JTI)
    │<──────── 5. Set New Cookies ─────────────────────┤
```

### 1. Dual Delivery Security Mechanism
To mitigate security vulnerabilities:
*   **HttpOnly Cookies:** JWT tokens are issued as HttpOnly, Secure, SameSite=Lax cookies. This renders them inaccessible to client-side scripts, protecting users from **Cross-Site Scripting (XSS)** attacks.
*   **Authorization Bearer Headers:** The FastAPI dependency layers also support standard `Authorization: Bearer <JWT>` headers to accommodate client integrations like mobile apps.

---

### 2. Refresh Token Rotation (RTR) Flow
To limit the risk of stolen token re-use:
1.  **JTI Registration:** Every refresh token contains a unique JWT ID claims string (`jti`). When a refresh token is issued, its `jti`, expiration time, and ownership are recorded in the `refresh_tokens` database table.
2.  **Rotation on Use:** When `/refresh` is called, the backend extracts the old token's `jti`, verifies that it is valid and has not been revoked, deletes or marks the old JTI record as revoked, and issues an entirely new Access/Refresh pair with a brand-new `jti`.
3.  **Logout Revocation:** Upon executing a logout request (`/logout`), the token's active database record is marked as **revoked** (`revoked_at = datetime.now(timezone.utc)`), invalidating future rotation attempts.

---

## 🔄 OAuth2 Identity Federation State Machine

`fast-backend` provides a robust, two-stage OAuth authentication process using **Authlib** client integrations to onboard Google and Apple users safely.

### OAuth Lifecycle State Diagram
```text
  [Initiation: /oauth/google/login]
                 │
                 ▼
     [Redirect to Provider OAuth Portal]
                 │
                 ▼
  [Callback Handshake: exchange code for profile]
                 │
                 ├─► User exists (or email matches) ──► [Authenticate immediately]
                 │                                      (Issue standard JWT cookies)
                 │
                 └─► New registration required ────────► [Issue ephemeral JWT]
                                                        (status: username_required)
                                                                 │
                                                                 ▼
                                                    [Complete: /complete-registration]
                                                    (Choose username, exchange token)
                                                                 │
                                                                 ▼
                                                        [User Registered]
```

### Flow Breakdown
1.  **Initiation:** The client hits `/oauth/google/login` specifying a callback `redirect_uri`. The backend generates a secure, randomized `state` string to prevent **Cross-Site Request Forgery (CSRF)**, registers it with the client redirect, and redirects to Google.
2.  **Callback Processing:** Google redirects the user back to `/oauth/google/callback`. The backend exchanges the one-time authorization code for an ID token and retrieves the user's profile info (email and external sub ID).
3.  **Check and Authenticate:**
    *   If an `OAuthAccount` record matching the provider user ID already exists, or if a user matches the retrieved email address, the user is authenticated immediately. Active session cookies are set, and the client receives a `USER_AUTHENTICATED` payload.
4.  **Pending Registration Sandbox:**
    *   If the user is new, the backend initiates a secure registration sandbox. Instead of writing incomplete user profiles with placeholder usernames, the backend issues an ephemeral **Pending Registration Token** (`OAuthPendingRegistrationData`). This token contains the verified provider details and has a short expiration window (e.g. 10 minutes).
5.  **Completion:** The client presents this ephemeral token and their desired custom username to `/oauth/complete-registration`. The backend decrypts the token, verifies its signature, asserts that the username is unique and meets character restrictions, creates the final `User` and `OAuthAccount` records, and completes authentication.
