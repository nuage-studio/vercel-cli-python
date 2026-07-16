import { createRequire as __createRequire } from 'node:module';
import { fileURLToPath as __fileURLToPath } from 'node:url';
import { dirname as __dirname_ } from 'node:path';
const require = __createRequire(import.meta.url);
const __filename = __fileURLToPath(import.meta.url);
const __dirname = __dirname_(__filename);
import {
  AGENT_REASON,
  AGENT_STATUS
} from "./chunk-IC4YEIGW.js";
import {
  getScope
} from "./chunk-DWU7JOO6.js";
import {
  getOrgById
} from "./chunk-DDEPCAGE.js";
import {
  buildCommandWithGlobalFlags,
  outputAgentError,
  shouldEmitNonInteractiveCommandError
} from "./chunk-CB3I3QIT.js";
import {
  output_manager_default
} from "./chunk-OX7KI3LF.js";

// src/util/projects/project-not-found-error.ts
async function printProjectNotFoundError(client, projectNameOrId, commandName, orgId) {
  let contextName;
  try {
    if (orgId) {
      const org = await getOrgById(client, orgId);
      contextName = org?.slug ?? orgId;
    } else {
      const scope = await getScope(client);
      contextName = scope.contextName;
    }
  } catch (err) {
    contextName = orgId;
    output_manager_default.debug(`Scope lookup failed during error reporting: ${err}`);
  }
  const scopeClause = contextName ? ` (${contextName})` : "";
  const headline = `Project "${projectNameOrId}" was not found in the current scope${scopeClause}.`;
  output_manager_default.error(
    `${headline}

If it lives in a different team or account:
  \u2022 Retry with \`--scope <team-slug|your-username>\`, or
  \u2022 Run \`vercel switch <team-slug|your-username>\` to change scope.

List accessible teams with \`vercel teams ls\`.`
  );
  if (!shouldEmitNonInteractiveCommandError(client)) {
    return;
  }
  const retryWithScope = buildCommandWithGlobalFlags(
    client.argv,
    `${commandName} --project ${projectNameOrId} --scope <team-slug>`
  );
  outputAgentError(
    client,
    {
      status: AGENT_STATUS.ERROR,
      reason: AGENT_REASON.PROJECT_NOT_FOUND,
      message: `${headline} If it lives in a different team or account, retry with --scope <team-slug|your-username> or run \`vercel switch <team-slug|your-username>\` to change scope.`,
      ...contextName ? { scope: contextName } : {},
      next: [
        { command: "vercel teams ls", when: "list accessible teams" },
        { command: retryWithScope, when: "retry with a specific team" },
        {
          command: "vercel switch <team-slug>",
          when: "change the default scope"
        }
      ]
    },
    1
  );
}

export {
  printProjectNotFoundError
};
