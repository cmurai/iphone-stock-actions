# iPhone pickup checker for GitHub Actions

Runs one check every 10 minutes, with optional Slack incoming-webhook alerts.
Python standard library only. Upload the contents of this directory to the root
of a GitHub repository, including `.github/workflows/stock.yml`, and commit to
the repository's default branch. A private repository keeps locations and stock
logs private; scheduled runs consume Actions usage according to your plan.

## Configure GitHub

Go to **Settings > Secrets and variables > Actions**.

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `APPLE_REQUEST_URL` | Apple fulfillment-messages request URL for your exact configuration and location (instructions below). |
| Secret, optional | `SLACK_WEBHOOK_URL` | Slack incoming webhook URL for your chosen channel. |
| Variable, optional | `APPLE_ZIP` | Override the ZIP/postal code in the Apple URL. |
| Variable, optional | `APPLE_PARTS` | Comma-separated exact Apple part numbers; overrides the parts in the URL. |
| Variable, optional | `APPLE_STORES` | Comma-separated store IDs, such as IDs printed by your first run. Blank checks every store Apple returns. |

Alternatively omit APPLE_REQUEST_URL and set both APPLE_ZIP and APPLE_PARTS
for the US storefront. No real SKU is supplied: select the correct Duo variant.

To get the request URL: open Apple's Duo purchase page on a desktop browser,
select color/storage/carrier/payment options, open Developer Tools > Network,
and check pickup with your ZIP. Find the successful `fulfillment-messages`
request and copy its Request URL. Do not copy cookies or a whole cURL command.
The script accepts the US or two-letter regional storefront on www.apple.com,
and www.apple.com.cn. It preserves the request's other configuration parameters.

## Slack (optional)

Create a Slack app at https://api.slack.com/apps, enable Incoming Webhooks,
choose **Add New Webhook to Workspace**, and authorize the intended channel.
Your workspace may require admin approval. Store the resulting URL only in the
GitHub secret named SLACK_WEBHOOK_URL. Do not commit it or paste it into chat.
Incoming webhooks post to the channel chosen during authorization.

Then open **Actions > iPhone pickup stock > Run workflow** on your default branch.
This runs a real check and, if any watched option is available, sends a real Slack
notification. With no webhook configured, results appear only in Actions logs.
No Slack message or GitHub deployment was performed while preparing this package.

## Alert behavior and schedule

- First observation: alert for any available watched option.
- Later observations: alert when an option changes from unavailable to available.
- Missing/unknown data preserves the last known state and never means out of stock.
- All newly available options are combined into one Slack message per run.
- Slack delivery failures fail the run and do not advance state, allowing a retry.
- Configuration or Slack destination changes reset the comparison on the next run.
- GitHub cache preserves observations between runners. Cache eviction/loss, a crash
  after Slack accepts a message, or a failed cache save can produce repeat alerts.
  This is best-effort deduplication, not exactly-once delivery.
- Schedule is minutes 7, 22, 37, and 52 each hour (UTC); one check per run, no --watch.
  For five-minute checks use `2-59/5 * * * *`. More checks use more Actions minutes.
- GitHub schedules run on the default branch and may be delayed or dropped under
  load. Public repositories' schedules can be disabled after 60 days of inactivity.
- A pickup offer may be for a future date. Confirm the displayed date at Apple.
- HTTP 401/403/429 and malformed inventory data fail visibly in Actions. Apple can
  reject hosted runners; this package does not bypass blocks. Enable GitHub workflow
  failure notifications to notice errors; stock errors are not sent to Slack.

## Validation and limitations

Parser and notification/state behavior are tested with mocked responses; no real
Slack message was sent. End-to-end Apple access and execution on a GitHub-hosted
runner have not been verified. Apple's endpoint is undocumented and may change.
This checks pickup availability, not physical unit counts, and never reserves stock.

Sources:
- https://orionchime.com/iphone-inventory-checker/
- https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://github.com/actions/cache

Run the included offline tests locally with `python -m unittest -v`.
