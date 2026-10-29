# User experience

**Status:** Current as of 2026-10-29.  
**Product name:** Monetra.  
**Companion:** `docs/architecture/AUTH_ARCHITECTURE.md`

An account is the email a person signs in with. A profile is one financial snapshot. Signing in does not create a profile.

## Signed out

The public site opens on the landing page. Sign in and Get started open the same panel.

Create account asks for email, a password of at least 12 characters, and a matching confirmation. Success sets a session and shows one screen: a confirmation link was sent to that address. That screen is only for a new account.

Sign in on an account that is already confirmed asks for the password, then a 6-digit code sent to that same address. The code screen names the address. The app opens after the code is accepted.

Sign in on an account that is not confirmed does not open the app. It sends the signup link again and says to confirm that link.

A wrong email or password is one sentence: **Email or password is incorrect.**

## Confirmation link

The mail button opens `/verify-email?id=&token=`. The page stays there. It does not send the person to the landing page, and it does not drop the token when the browser has no session.

Pressing **Confirm email** is what uses the link. If a session from signup is still present and the address is now confirmed, the app opens Profile. If there is no session, the page says the email is confirmed and offers **Sign in**. That sign-in uses the code, not another confirmation link.

Password reset (`/reset-password`) and email change (`/confirm-email`) keep their query the same way. Opening those pages does not use the secret.

## Signed in

The shell shows the account email, Settings, and Sign out. Settings holds change password, change email, and delete account.

Dashboard, Advisory, Chat, and Goals need a profile. Settings does not. Sign out revokes only this browser's session and returns to the landing page. The back button does not reopen another account's profile.

## What the person is not asked to do

They are not asked to paste an API key. They are not asked to confirm the signup link on every later sign-in. Goal plans stay in the browser. There is no profile-edit form.
