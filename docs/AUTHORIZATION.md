# Authentication and Authorization

This project uses Django's built-in User model, Django REST Framework, and Simple JWT. User roles are stored in the related `accounts.UserProfile` model.

## Roles

- `CUSTOMER`: assigned automatically at public registration.
- `AGENT`: support agent; assign through the admin-only role endpoint or Django admin.
- `ADMIN`: application administrator; assign only through a trusted administrator workflow.

Public registration never accepts a role field. A user cannot promote their own account.

Django staff and superusers are treated as administrators by the authorization permission classes.

## Install and migrate

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Configure `DJANGO_SECRET_KEY` and `GOOGLE_CLIENT_ID` as environment variables. Google sign-in remains disabled until a valid OAuth web client ID is configured.

## API endpoints

All paths are relative to `/api/auth/`.

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| POST | `register/` | Public | Register a customer; returns access and refresh tokens |
| POST | `login/` | Public | Email/password login |
| POST | `google/` | Public | Verify a Google ID token on the server and sign in |
| GET | `me/` | Access token | Return the current user's profile |
| POST | `token/refresh/` | Refresh token | Issue a new access token |
| POST | `logout/` | Access token + refresh token in body | Blacklist the supplied refresh token |
| PATCH | `users/<user_id>/role/` | Admin | Assign CUSTOMER, AGENT, or ADMIN |

### Register

```http
POST /api/auth/register/
Content-Type: application/json
```

```json
{
  "first_name": "Test",
  "last_name": "Customer",
  "email": "customer@example.com",
  "password": "Use-A-Strong-Unique-Password-928!"
}
```

Registration always creates a CUSTOMER profile. Passwords are validated with Django's configured password validators and stored as hashes.

### Login

```json
{
  "email": "customer@example.com",
  "password": "Use-A-Strong-Unique-Password-928!"
}
```

The response includes `access` and `refresh`. Keep both tokens private.

### Call a protected endpoint

Send the access token in the HTTP header:

```http
Authorization: Bearer <access-token>
```

The configured access lifetime is 30 minutes. The refresh lifetime is 7 days.

### Refresh

```http
POST /api/auth/token/refresh/
Content-Type: application/json
```

```json
{
  "refresh": "<refresh-token>"
}
```

With refresh rotation enabled, use the newly returned refresh token as well as the new access token.

### Logout

```http
POST /api/auth/logout/
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "refresh": "<refresh-token>"
}
```

Logout blacklists the supplied refresh token. Clients should discard both tokens locally. Access tokens are stateless and remain valid until their short expiry unless an additional revocation strategy is implemented.

### Google sign-in

The client sends a Google ID token, not an email address or user profile supplied by the browser:

```json
{
  "id_token": "<google-id-token>"
}
```

The backend verifies the token signature and audience against `GOOGLE_CLIENT_ID`, requires a verified email, and links the stable Google `sub` claim to the profile. Do not accept an unverified client-side email as proof of identity.

### Change a user's role

Only a Django staff/superuser or a profile with ADMIN role can call:

```http
PATCH /api/auth/users/<user_id>/role/
Authorization: Bearer <admin-access-token>
Content-Type: application/json
```

```json
{
  "role": "AGENT"
}
```

Use the Django admin or a trusted administrator account to grant initial administrator access. Never expose a public endpoint that lets users select their own role.

## Tests

Run the authentication and authorization test suite:

```powershell
python manage.py test accounts
```

The tests cover customer registration, duplicate email rejection, login, protected profile access, refresh, logout token blacklisting, and admin-only role changes.
