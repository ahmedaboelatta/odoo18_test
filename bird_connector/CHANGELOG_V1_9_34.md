# V1.9.34 - Realtime Inbox Reliability

- Added server-pushed inbox refresh events for inbound WhatsApp messages.
- Inbox now reacts immediately to Bird message status events as well as conversation events.
- Team, assignment, take, close/reopen and read changes notify other open operator inboxes.
- Reduced inbox polling from 5 seconds to a 30-second fallback; Odoo Bus is now the primary realtime path.
- Kept optimistic sending so replies appear immediately without a full page reload.
- Preserved portable multi-database deployment behavior.
