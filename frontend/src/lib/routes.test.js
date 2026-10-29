import assert from "node:assert/strict";
import test from "node:test";
import { isMailLink, locationForSamePath, resolveRoute } from "./routes.js";

test("the email-change link stays on its page", () => {
  const decision = resolveRoute({ signedIn: false, path: "/confirm-email", profileId: null });
  assert.equal(decision.screen, "confirm-email");
  assert.equal(decision.redirect, null);
});

test("the reset link stays on its page", () => {
  const decision = resolveRoute({ signedIn: false, path: "/reset-password", profileId: null });
  assert.equal(decision.screen, "reset-password");
  assert.equal(decision.redirect, null);
});

test("the verification link stays on its page", () => {
  const decision = resolveRoute({ signedIn: false, path: "/verify-email", profileId: null });
  assert.equal(decision.screen, "verify-email");
  assert.equal(decision.redirect, null);
  assert.equal(isMailLink("/verify-email"), true);
  assert.equal(isMailLink("/"), false);
});

test("staying on the verification link keeps the token", () => {
  assert.equal(
    locationForSamePath("/verify-email", "/verify-email", "?id=4&token=abc", ""),
    "/verify-email?id=4&token=abc",
  );
});

test("leaving the verification link drops the token", () => {
  assert.equal(
    locationForSamePath("/", "/verify-email", "?id=4&token=abc", ""),
    "/",
  );
});

test("signed out /chat renders the landing page and remembers the path", () => {
  const decision = resolveRoute({ signedIn: false, path: "/chat", profileId: null });
  assert.equal(decision.screen, "landing");
  assert.equal(decision.remember, "/chat");
  assert.equal(decision.redirect, null);
});

test("signed in with no profile on /goals renders /profile", () => {
  const decision = resolveRoute({ signedIn: true, path: "/goals", profileId: null });
  assert.equal(decision.screen, "profile");
  assert.equal(decision.redirect, "/profile");
});

test("signed in on /settings stays on settings without a profile", () => {
  const decision = resolveRoute({ signedIn: true, path: "/settings", profileId: null });
  assert.equal(decision.screen, "settings");
  assert.equal(decision.redirect, null);
});

test("signed out /settings remembers the path", () => {
  const decision = resolveRoute({ signedIn: false, path: "/settings", profileId: null });
  assert.equal(decision.screen, "landing");
  assert.equal(decision.remember, "/settings");
  assert.equal(decision.redirect, null);
});

test("signed in with a profile on /advisory renders advisory", () => {
  const decision = resolveRoute({ signedIn: true, path: "/advisory", profileId: 4 });
  assert.equal(decision.screen, "advisory");
  assert.equal(decision.redirect, null);
});
