import assert from "node:assert/strict";
import test from "node:test";
import { shouldAttemptRefresh } from "./sessionRefresh.js";

test("a dead access cookie refreshes once", () => {
  assert.equal(
    shouldAttemptRefresh({ code: "session_expired", path: "/auth/me", alreadyRetried: false }),
    true,
  );
});

test("a second 401 does not refresh again", () => {
  assert.equal(
    shouldAttemptRefresh({ code: "session_expired", path: "/users", alreadyRetried: true }),
    false,
  );
});

test("the refresh call itself does not refresh", () => {
  assert.equal(
    shouldAttemptRefresh({ code: "session_expired", path: "/auth/refresh", alreadyRetried: false }),
    false,
  );
});

test("other 401 codes do not refresh", () => {
  assert.equal(
    shouldAttemptRefresh({ code: "unauthorized", path: "/users", alreadyRetried: false }),
    false,
  );
});
