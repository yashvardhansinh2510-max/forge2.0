// The native SDK is intentionally not part of the browser bootstrap. Browser
// monitoring is opt-in and is handled by the hosting/runtime observability
// layer, while this keeps shared native route discovery from pulling Sentry
// and its tracing stack into every web route.
module.exports = {
  init() {},
  captureException() {},
  captureMessage() {},
  setUser() {},
  setTag() {},
  setContext() {},
  addBreadcrumb() {},
};
