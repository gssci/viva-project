from typing import Optional

from langchain_core.tools import tool

from .core import (
    applescript_list,
    escape_applescript_string,
    parse_csv_values,
    run_applescript,
)


def _recipient_script(recipient_kind: str, addresses: list[str]) -> str:
    if not addresses:
        return ""
    lines = [f"set {recipient_kind}Addresses to {applescript_list(addresses)}"]
    lines.append(f"repeat with recipientAddress in {recipient_kind}Addresses")
    lines.append(
        f"    make new {recipient_kind} recipient at end of {recipient_kind} recipients "
        "with properties {address:(recipientAddress as text)}"
    )
    lines.append("end repeat")
    return "\n            ".join(lines)


@tool
def search_mac_contacts(query: str, max_results: int = 10) -> str:
    """
    Searches Contacts by name and returns names plus available email and phone values.
    Call this tool when the user asks to find a contact or needs an email/phone lookup.

    Args:
        query: Contact name text to search for.
        max_results: Maximum contacts to return, from 1 to 20.
    """
    if not query.strip():
        return "Contact search text cannot be empty."

    max_results = max(1, min(20, max_results))
    safe_query = escape_applescript_string(query)
    script = f'''
    tell application "Contacts"
        set output to ""
        set matchCount to 0
        set matchingPeople to (every person whose name contains "{safe_query}")
        repeat with p in matchingPeople
            set matchCount to matchCount + 1
            set output to output & "- " & name of p

            set emailOutput to ""
            repeat with e in emails of p
                try
                    set emailOutput to emailOutput & value of e & ", "
                end try
            end repeat
            if emailOutput is not "" then set output to output & " | emails: " & emailOutput

            set phoneOutput to ""
            repeat with ph in phones of p
                try
                    set phoneOutput to phoneOutput & value of ph & ", "
                end try
            end repeat
            if phoneOutput is not "" then set output to output & " | phones: " & phoneOutput

            set output to output & "\\n"
            if matchCount is greater than or equal to {max_results} then return output
        end repeat
        if output is "" then return "No contacts found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def get_mac_contact_details(name_query: str) -> str:
    """
    Returns details for a single matching contact.
    Call this tool when the user asks for a contact's email addresses or phone numbers.

    Args:
        name_query: Contact name text to search for.
    """
    if not name_query.strip():
        return "Contact search text cannot be empty."

    safe_query = escape_applescript_string(name_query)
    script = f'''
    tell application "Contacts"
        set matches to (every person whose name contains "{safe_query}")
        if (count of matches) = 0 then return "No matching contact found."
        if (count of matches) > 1 then return "Multiple matching contacts found. Please provide a more specific name."
        set p to item 1 of matches

        set output to name of p & "\\n"
        repeat with e in emails of p
            try
                set output to output & "- email (" & label of e & "): " & value of e & "\\n"
            end try
        end repeat
        repeat with ph in phones of p
            try
                set output to output & "- phone (" & label of ph & "): " & value of ph & "\\n"
            end try
        end repeat
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def list_mail_message_summaries(
    query: Optional[str] = None,
    unread_only: bool = False,
    mailbox_name: Optional[str] = "INBOX",
    max_results: int = 10,
    include_snippets: bool = True,
) -> str:
    """
    Lists Mail messages with sender, subject, date, mailbox, unread state, and optional short snippets.
    Call this tool when the user asks about unread, recent, or searched email.

    Args:
        query: (Optional) Text to match in sender, subject, or content.
        unread_only: True to return only unread messages.
        mailbox_name: Mailbox name to search. Defaults to INBOX.
        max_results: Maximum messages to return, from 1 to 25.
        include_snippets: True to include short message body snippets.
    """
    max_results = max(1, min(25, max_results))
    safe_query = escape_applescript_string(query)
    safe_mailbox = escape_applescript_string(mailbox_name or "INBOX")
    unread_value = "true" if unread_only else "false"
    snippets_value = "true" if include_snippets else "false"
    script = f'''
    tell application "Mail"
        set maxResults to {max_results}
        set queryText to "{safe_query}"
        set unreadOnly to {unread_value}
        set includeSnippets to {snippets_value}
        try
            if "{safe_mailbox}" is "INBOX" then
                set targetMessages to messages of inbox
                set mailboxLabel to "INBOX"
            else
                set targetMessages to messages of mailbox "{safe_mailbox}"
                set mailboxLabel to "{safe_mailbox}"
            end if
        on error
            return "Mailbox not found."
        end try

        set output to ""
        set messageCount to 0
        repeat with m in targetMessages
            if messageCount is greater than or equal to maxResults then exit repeat
            set shouldInclude to true
            if unreadOnly and read status of m then set shouldInclude to false

            set messageContent to ""
            if shouldInclude then
                try
                    set messageContent to content of m as text
                end try
                if queryText is not "" then
                    if subject of m does not contain queryText and sender of m does not contain queryText and messageContent does not contain queryText then
                        set shouldInclude to false
                    end if
                end if
            end if

            if shouldInclude then
                set messageCount to messageCount + 1
                set unreadLabel to "read"
                if read status of m is false then set unreadLabel to "unread"
                set output to output & "- " & sender of m & " | " & subject of m & " | " & (date received of m as string) & " | " & mailboxLabel & " | " & unreadLabel
                if includeSnippets then
                    set cleanContent to do shell script "printf %s " & quoted form of messageContent & " | tr '\\\\r\\\\n' '  ' | cut -c 1-180"
                    if cleanContent is not "" then set output to output & " | " & cleanContent
                end if
                set output to output & "\\n"
            end if
        end repeat

        if output is "" then return "No matching mail messages found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def create_mail_draft(
    to_recipients: str,
    subject: str,
    body: str,
    cc_recipients: Optional[str] = "",
    bcc_recipients: Optional[str] = "",
) -> str:
    """
    Creates a visible Mail draft without sending it.
    Call this tool when the user asks to draft or prepare an email.

    Args:
        to_recipients: Comma-separated recipient email addresses.
        subject: Email subject.
        body: Email body.
        cc_recipients: (Optional) Comma-separated CC addresses.
        bcc_recipients: (Optional) Comma-separated BCC addresses.
    """
    recipients = parse_csv_values(to_recipients)
    if not recipients or not subject.strip() or not body.strip():
        return "Recipient, subject, and body are required to create a mail draft."

    safe_subject = escape_applescript_string(subject)
    safe_body = escape_applescript_string(body)
    cc_addresses = parse_csv_values(cc_recipients)
    bcc_addresses = parse_csv_values(bcc_recipients)
    script = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:true}}
        tell newMessage
            {_recipient_script("to", recipients)}
            {_recipient_script("cc", cc_addresses)}
            {_recipient_script("bcc", bcc_addresses)}
        end tell
        activate
        return "Mail draft created."
    end tell
    '''
    return run_applescript(script)


@tool
def send_mail_message(
    to_recipients: str,
    subject: str,
    body: str,
    cc_recipients: Optional[str] = "",
    bcc_recipients: Optional[str] = "",
) -> str:
    """
    Sends an email through Apple Mail. Requires explicit recipient, subject, and body.
    Call this tool only when the user clearly asks to send an email.

    Args:
        to_recipients: Comma-separated recipient email addresses.
        subject: Email subject.
        body: Email body.
        cc_recipients: (Optional) Comma-separated CC addresses.
        bcc_recipients: (Optional) Comma-separated BCC addresses.
    """
    recipients = parse_csv_values(to_recipients)
    if not recipients or not subject.strip() or not body.strip():
        return "Recipient, subject, and body are required to send email."

    safe_subject = escape_applescript_string(subject)
    safe_body = escape_applescript_string(body)
    cc_addresses = parse_csv_values(cc_recipients)
    bcc_addresses = parse_csv_values(bcc_recipients)
    script = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
        tell newMessage
            {_recipient_script("to", recipients)}
            {_recipient_script("cc", cc_addresses)}
            {_recipient_script("bcc", bcc_addresses)}
        end tell
        send newMessage
        return "Email sent."
    end tell
    '''
    return run_applescript(script)


mail_contact_tools = [
    search_mac_contacts,
    get_mac_contact_details,
    list_mail_message_summaries,
    create_mail_draft,
    send_mail_message,
]
