// Zabbix 7.0 media type "bridgeai ops hook" (type: Webhook). Import by hand: Alerts > Media types > Create > Webhook.
// Script parameters (name = value), the macros are Zabbix's:
//   url          = http://<this-vm-lan-address>:8660/event      (ZBX_HOOK_BIND of ops/zabbix_hook.py)
//   token        = <ZBX_HOOK_TOKEN>                             (put it in a {$BRIDGEAI_HOOK_TOKEN} secret macro, not in clear)
//   event_id     = {EVENT.ID}
//   status       = {EVENT.STATUS}                               PROBLEM or OK (to confirm on 7.0.22 for the recovery operation)
//   name         = {EVENT.NAME}
//   severity     = {EVENT.SEVERITY}
//   host         = {HOST.NAME}
//   tags         = {EVENT.TAGSJSON}                             [{"tag":"unit","value":"x"}, ...]
// Message template: none needed (this script ignores {ALERT.MESSAGE}); the receiver builds the text from the tags.
// Process only the problem and recovery operations in the action; leave "update operations" empty.
var params = JSON.parse(value);
var tags = [];
try {
    tags = JSON.parse(params.tags);
} catch (e) {
    tags = [];   // an unreadable tag list is not worth losing the alert: the receiver says "SIN UNIDAD"
}
var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
req.addHeader('X-Zabbix-Token: ' + params.token);
var body = JSON.stringify({
    event_id: params.event_id,
    status: params.status,
    name: params.name,
    severity: params.severity,
    host: params.host,
    tags: tags
});
var resp = req.post(params.url, body);
if (req.getStatus() !== 200) {
    // Zabbix marks the notification failed and retries it (media type attempts); the receiver is idempotent per event id.
    throw 'ops hook answered ' + req.getStatus() + ': ' + resp;
}
return 'ok';
