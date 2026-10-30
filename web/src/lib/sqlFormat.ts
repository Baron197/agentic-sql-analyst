// Readable layout for the one-line SQL the validator regenerates: each main clause starts
// a new line, indented by parenthesis depth. Display only; string literals are untouched.

const CLAUSE =
  /\s+(SELECT|FROM|(?:LEFT|RIGHT|FULL|INNER|CROSS)\s+JOIN|JOIN|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|UNION(?:\s+ALL)?)\b/g;
const STRING_LITERAL = /('(?:[^']|'')*')/;

const depthChange = (text: string) =>
  (text.match(/\(/g)?.length ?? 0) - (text.match(/\)/g)?.length ?? 0);

export function formatSql(sql: string): string {
  let depth = 0;
  let out = "";
  for (const part of sql.split(STRING_LITERAL)) {
    if (part.startsWith("'")) {
      out += part;
      continue;
    }
    let last = 0;
    for (const m of part.matchAll(CLAUSE)) {
      const before = part.slice(last, m.index);
      depth += depthChange(before);
      out += before + "\n" + "  ".repeat(Math.max(0, depth)) + m[1].replace(/\s+/g, " ");
      last = m.index + m[0].length;
    }
    const tail = part.slice(last);
    depth += depthChange(tail);
    out += tail;
  }
  return out.trim();
}
