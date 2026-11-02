// Links to the public repository (docs and committed result files).

export const REPO = "https://github.com/Baron197/agentic-sql-analyst";

/** A file in the repository on GitHub, e.g. repoFile("docs/SECURITY.md"). */
export const repoFile = (path: string) => `${REPO}/blob/main/${path}`;
