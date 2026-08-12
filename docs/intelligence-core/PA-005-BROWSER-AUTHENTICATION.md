# PA-005 Browser Authentication Architecture

Status: repository implementation validated; Entra redirect configuration required

## Failure and root cause

The first owner-attended device-code attempt returned `AADSTS530035` /
`BlockedBySecurityDefaults`. Microsoft documents that Security Defaults blocks
device-code flow. The attempt did not obtain an access token and made zero
successful Microsoft Graph source reads. Security Defaults and all tenant
security controls remain unchanged.

## Replacement flow

PA-005 now uses Microsoft Authentication Library (MSAL) system-browser
interactive authentication for a public client. MSAL performs authorization code
flow with PKCE and listens temporarily on loopback port 8400. It uses the exact
tenant, client, account hint and Graph scopes already approved. There is no
client secret and no serialized token cache; token state exists only in process
memory.

Before any Graph request, the credential requires ID-token tenant and preferred
username claims to match PA-005 and requires the granted Graph scope set to equal
`User.Read`, `Calendars.Read` and `Mail.Read`. `User.Read` is used only to verify
the signed-in `/me` identity. Protocol scopes such as `openid` and `profile`
are not Graph permissions. Existing connector and source boundaries are
unchanged.

## Required owner-admin Entra configuration

For the dedicated single-tenant **EDN Intelligence Core** application
`2381e4f6-44bc-4697-ad64-e86513cb9dee` in tenant
`aae6ab79-45eb-4829-a04f-595becdb936d`:

1. Open **Microsoft Entra admin center > App registrations > the application >
   Authentication**.
2. Under **Platform configurations**, add **Mobile and desktop applications**
   with redirect URI exactly `http://localhost` (or verify it already exists on
   that platform). Microsoft ignores the ephemeral port when matching localhost
   native-app redirects, so the runtime URI on port 8400 matches this entry.
3. Verify **Allow public client flows** is **Yes**. Do not add a secret, web/SPA
   redirect, application permission, SharePoint permission, or broader delegated
   permission.
4. Under **API permissions**, verify the only PA-005 Microsoft Graph delegated
   permissions are exactly `User.Read`, `Calendars.Read` and `Mail.Read`.
   `User.Read` is restricted in PA-005 to authenticated-user identity verification.

Do not weaken Security Defaults, Conditional Access, MFA or device controls.

## Retry command after owner confirmation

```bash
python -m edn.intelligence.pa005_activation validate-live \
  --output "/mnt/f/EDN OS/Working/Owner Intelligence Beta/PA-005/2026-08-12/microsoft-live-validation.json"
```

The output remains no-clobber. A retry requires explicit owner confirmation that
the Entra configuration above is complete; repository validation alone does not
authorise another authentication attempt.
