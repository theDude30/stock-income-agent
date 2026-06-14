import { setupServer } from "msw/node";

// Tests register their own handlers via server.use(...). Unhandled requests
// error so a missing mock fails loudly instead of hanging.
export const server = setupServer();
