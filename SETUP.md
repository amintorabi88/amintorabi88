# Amin's automatic profile statistics

This replaces “My work / Explore my projects” with contribution statistics from
the past 365 days. Your existing portrait and introduction stay in place.
Each displayed number combines public and accessible private activity: Commits,
PRs, Reviews, and Issues. There is no breakdown by repository or company.

## 1. Put the files in your public profile repository

Repository: https://github.com/amintorabi88/amintorabi88

The included `repository` folder in the ZIP has this structure:

```
README.md
portrait-dark.svg
portrait-light.svg
scripts/update_stats.py
.github/workflows/update-stats.yml
```

Replace the existing README with this version, or copy its new stats section into
your existing table. Keep both `<!-- STATS:START -->` and `<!-- STATS:END -->`.
Do not introduce blank lines or indentation inside the HTML table.

In the GitHub web interface, use Add file → Create new file to create the two
nested files. Enter their full paths exactly as above and paste the supplied
contents. The `.github` folder may be hidden in Finder; creating the workflow
through GitHub avoids this issue. Commit everything to the default branch.
The portraits are the corrected versions; you can keep your current copies.

## 2. Enable private contribution visibility

On your GitHub profile, above the contribution graph, choose Contribution settings
→ Private contributions. This permits anonymized private contribution counts in
your public profile. It does not grant a token access to company repositories.

## 3. Create a token for reading your own contribution statistics

Open https://github.com/settings/tokens and choose Generate new token (classic).
Give it a recognizable name and an expiration date. Start with only `read:user`
selected. GitHub's ContributionsCollection documentation specifies this scope
for including private/internal contributions. Do not select `repo` by default:
it is a much broader permission and is not a read-only permission.

The token must belong to `amintorabi88`. The script verifies that identity.
Never paste a token into the README, source code, chat, or a workflow file.

For company activity, results depend on organization restrictions and what GitHub
exposes to the token. Classic tokens may require Configure SSO → Authorize for the
organization. An organization may block classic tokens entirely. If company
activity is missing, use your organization's approved authentication method;
do not assume that making a broader token will resolve the restriction.
The script also accepts a user personal token permitted by your organization if
it can execute this GraphQL query. Fine-grained permissions and approval depend
on the organization; this package does not claim a universal fine-grained setup.

## 4. Save the token as a repository secret

In your profile repository, open Settings → Secrets and variables → Actions →
New repository secret. Use this exact name:

```
PROFILE_STATS_TOKEN
```

Paste the token as the value. GitHub stores it separately from public files.
The workflow exposes it only to the aggregate-statistics step. The separate,
built-in GITHUB_TOKEN saves the README; it does not read company activity.

## 5. Run once, then let it update daily

Open Actions → Update profile stats → Run workflow. After a successful run,
refresh your profile. The workflow is scheduled daily at 06:17 UTC. Actual start
time depends on GitHub's scheduler. Renew the secret when its token expires.

If pushing the README fails, check repository Actions write permissions and
default-branch rules. The workflow requests contents:write but cannot override
repository or organization restrictions. An API failure preserves existing
statistics rather than replacing them with zeroes.

## What the numbers mean

- These are GitHub contribution-calendar statistics, not every commit on every branch.
- PRs means pull requests opened during the window, not PRs merged.
- Contributions to other owners' repositories can count, including company work
  when accessible; the query is not limited to repositories you own.
- Completeness depends on GitHub's visibility and contribution rules.
  Restricted contributions are not treated as commits. If GitHub reports them,
  the README shows a note that some private activity may be missing from the totals.
- No repository names, links, titles, code, or per-repository counts are queried.
  Publishing daily totals still makes those aggregate numbers public.
- This package queries GitHub.com for this account. Activity under another
  account or on a separate company GitHub Enterprise Server is not directly fetched.

## Verification

The README generation and failure handling were checked locally using synthetic
data. Live private-company totals require your token and have not been verified.
After setup, compare the same 365-day window while signed into GitHub.

## Sources

- Contribution fields and read:user scope: https://docs.github.com/en/graphql/reference/users#contributionscollection
- Private contribution visibility: https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/manage-visibility-settings-for-private-contributions-and-achievements
- SSO token authorization: https://docs.github.com/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on
- Organization token restrictions: https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/setting-a-personal-access-token-policy-for-your-organization
