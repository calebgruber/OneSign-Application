// OneSign Windows Credential Provider
// CredentialTile.cs — ICredentialProviderCredential implementation
//
// Represents the single "Tap your badge" tile that appears on the Windows
// lock / logon screen.  When the OneSign agent writes credentials to the
// named pipe, the PipeServer fires CredentialsReceived, we store the creds,
// signal the tile, and LogonUI calls GetSerialization to finalize authentication.

using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace OneSign.CredentialProvider
{
    [ComVisible(true)]
    internal sealed class CredentialTile : ICredentialProviderCredential
    {
        // Field IDs — must match the descriptors returned by CredProvider
        internal const uint FIELD_TILE_LABEL    = 0;
        internal const uint FIELD_STATUS_LABEL  = 1;
        internal const uint FIELD_PASSWORD      = 2;
        internal const uint FIELD_SUBMIT        = 3;

        private ICredentialProviderCredentialEvents? _events;
        private IntPtr _adviseContext;

        // Credentials delivered by the agent
        private string? _username;
        private string? _password;
        private string? _domain;
        private bool    _credReady;

        // NTLM/Kerberos authentication package index (resolved once)
        private uint _authPackageIndex;

        public CredentialTile(uint authPackageIndex)
        {
            _authPackageIndex = authPackageIndex;
        }

        // ── Called by CredProvider when agent delivers credentials ────────────

        public void DeliverCredentials(AgentCredentials creds)
        {
            _username  = creds.Username;
            _password  = creds.Password;
            _domain    = creds.Domain;
            _credReady = true;

            // Notify LogonUI that credentials are ready.
            // The call must be made on a background thread to avoid deadlocking
            // LogonUI's message pump.  LogonUI will then call GetSerialization.
            ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    _events?.CredentialsChanged(_adviseContext);
                }
                catch { /* best-effort */ }
            });
        }

        // ── ICredentialProviderCredential ─────────────────────────────────────

        public int Advise(ICredentialProviderCredentialEvents pcpce)
        {
            _events = pcpce;
            if (pcpce is ICredentialProviderCredentialEvents2 e2)
                _adviseContext = e2.GetAdviseContext();
            return 0; // S_OK
        }

        public int UnAdvise()
        {
            _events = null;
            return 0;
        }

        public int SetSelected(out bool pbAutoLogon)
        {
            pbAutoLogon = false;
            return 0;
        }

        public int SetDeselected() => 0;

        public int GetFieldState(uint dwFieldID,
            out CREDENTIAL_PROVIDER_FIELD_STATE cpfs,
            out CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE cpfis)
        {
            switch (dwFieldID)
            {
                case FIELD_TILE_LABEL:
                    cpfs   = CREDENTIAL_PROVIDER_FIELD_STATE.CPFS_DISPLAY_IN_BOTH;
                    cpfis  = CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_NONE;
                    return 0;

                case FIELD_STATUS_LABEL:
                    cpfs   = CREDENTIAL_PROVIDER_FIELD_STATE.CPFS_DISPLAY_IN_SELECTED_TILE;
                    cpfis  = CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_NONE;
                    return 0;

                case FIELD_PASSWORD:
                    cpfs   = CREDENTIAL_PROVIDER_FIELD_STATE.CPFS_DISPLAY_IN_SELECTED_TILE;
                    cpfis  = _credReady
                           ? CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_NONE
                           : CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_FOCUSED;
                    return 0;

                case FIELD_SUBMIT:
                    cpfs   = CREDENTIAL_PROVIDER_FIELD_STATE.CPFS_DISPLAY_IN_SELECTED_TILE;
                    cpfis  = CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_NONE;
                    return 0;

                default:
                    cpfs   = CREDENTIAL_PROVIDER_FIELD_STATE.CPFS_HIDDEN;
                    cpfis  = CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE.CPFIS_NONE;
                    return unchecked((int)0x80070057); // E_INVALIDARG
            }
        }

        public int GetStringValue(uint dwFieldID, out string? ppsz)
        {
            switch (dwFieldID)
            {
                case FIELD_TILE_LABEL:
                    ppsz = "OneSign — Tap your badge";
                    return 0;

                case FIELD_STATUS_LABEL:
                    ppsz = _credReady
                         ? "Badge read — signing in…"
                         : "Waiting for badge tap…";
                    return 0;

                case FIELD_PASSWORD:
                    ppsz = _credReady ? (_password ?? "") : "";
                    return 0;

                default:
                    ppsz = null;
                    return unchecked((int)0x80070057);
            }
        }

        public int GetBitmapValue(uint dwFieldID, out IntPtr phbmp)
        {
            phbmp = IntPtr.Zero;
            return unchecked((int)0x80004001); // E_NOTIMPL
        }

        public int GetCheckboxValue(uint dwFieldID,
            out bool pbChecked, out string? ppszLabel)
        {
            pbChecked = false;
            ppszLabel = null;
            return unchecked((int)0x80070057);
        }

        public int GetSubmitButtonValue(uint dwFieldID, out uint pdwAdjacentTo)
        {
            pdwAdjacentTo = FIELD_PASSWORD;
            return 0;
        }

        public int GetComboBoxValueCount(uint dwFieldID,
            out uint pcItems, out uint pdwSelectedItem)
        {
            pcItems        = 0;
            pdwSelectedItem = 0;
            return unchecked((int)0x80070057);
        }

        public int GetComboBoxValueAt(uint dwFieldID, uint dwItem, out string? ppszItem)
        {
            ppszItem = null;
            return unchecked((int)0x80070057);
        }

        public int SetStringValue(uint dwFieldID, string psz)
        {
            // Allow user to type a password in the fallback password field
            if (dwFieldID == FIELD_PASSWORD)
            {
                _password  = psz;
                _username  = null;  // Manual entry — domain/user unknown until submit
                _credReady = true;
                return 0;
            }
            return unchecked((int)0x80070057);
        }

        public int SetCheckboxValue(uint dwFieldID, bool bChecked)
            => unchecked((int)0x80070057);

        public int SetComboBoxSelectedValue(uint dwFieldID, uint dwSelectedItem)
            => unchecked((int)0x80070057);

        public int CommandLinkClicked(uint dwFieldID)
            => unchecked((int)0x80004001);

        public int GetSerialization(
            out CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE pcpgsr,
            out CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION   pcpcs,
            out string? ppszOptionalStatusText,
            out uint    pcpsiOptionalStatusIcon)
        {
            ppszOptionalStatusText  = null;
            pcpsiOptionalStatusIcon = 0;

            if (!_credReady || string.IsNullOrEmpty(_password))
            {
                pcpgsr = CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE.CPGSR_NO_CREDENTIAL_NOT_FINISHED;
                pcpcs  = default;
                return 0;
            }

            try
            {
                pcpcs = BuildSerialization(_username ?? "", _password!, _domain ?? ".");
                pcpgsr = CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE.CPGSR_RETURN_CREDENTIAL_FINISHED;
                return 0;
            }
            catch (Exception ex)
            {
                ppszOptionalStatusText = ex.Message;
                pcpgsr = CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE.CPGSR_NO_CREDENTIAL_NOT_FINISHED;
                pcpcs  = default;
                return unchecked((int)0x80004005); // E_FAIL
            }
        }

        public int ReportResult(int ntsStatus, int ntsSubstatus,
            out string? ppszOptionalStatusText, out uint pcpsiOptionalStatusIcon)
        {
            ppszOptionalStatusText  = null;
            pcpsiOptionalStatusIcon = 0;
            // Reset on failure so the tile is ready for another badge tap
            if (ntsStatus != 0)
            {
                _credReady = false;
                _username  = null;
                _password  = null;
            }
            return 0;
        }

        // ── Serialization helper ──────────────────────────────────────────────

        private CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION BuildSerialization(
            string username, string password, string domain)
        {
            // Pack a KERB_INTERACTIVE_UNLOCK_LOGON structure in a flat byte buffer.
            // All UNICODE_STRING.Buffer pointers are offsets relative to the start
            // of the buffer; Windows Credential infrastructure re-bases them when
            // deserializing.

            byte[] domainBytes   = Encoding.Unicode.GetBytes(domain);
            byte[] usernameBytes = Encoding.Unicode.GetBytes(username);
            byte[] passwordBytes = Encoding.Unicode.GetBytes(password);

            // Layout: header (fixed-size struct) + string data
            int headerSize = Marshal.SizeOf<KERB_INTERACTIVE_UNLOCK_LOGON>();
            int totalSize  = headerSize
                           + domainBytes.Length
                           + usernameBytes.Length
                           + passwordBytes.Length;

            IntPtr buffer = Marshal.AllocCoTaskMem(totalSize);

            try
            {
                // Zero the header
                for (int i = 0; i < headerSize; i++)
                    Marshal.WriteByte(buffer, i, 0);

                // Write string payloads
                int domainOffset   = headerSize;
                int usernameOffset = domainOffset   + domainBytes.Length;
                int passwordOffset = usernameOffset + usernameBytes.Length;

                for (int i = 0; i < domainBytes.Length;   i++)
                    Marshal.WriteByte(buffer, domainOffset   + i, domainBytes[i]);
                for (int i = 0; i < usernameBytes.Length; i++)
                    Marshal.WriteByte(buffer, usernameOffset + i, usernameBytes[i]);
                for (int i = 0; i < passwordBytes.Length; i++)
                    Marshal.WriteByte(buffer, passwordOffset + i, passwordBytes[i]);

                // Patch KERB_INTERACTIVE_LOGON fields (MessageType already 0 = KerbInteractiveLogon,
                // which Windows maps to KerbWorkstationUnlockLogon at submit time).
                // We use offsets from the start of the buffer as the UNICODE_STRING.Buffer values;
                // the framework re-bases these before passing to LSA.

                // Struct layout (x64):
                //   +0:  KERB_INTERACTIVE_LOGON.MessageType  (uint, 4 bytes)
                //   +4:  (4 bytes padding)
                //   +8:  LogonDomainName.Length              (ushort)
                //   +10: LogonDomainName.MaximumLength        (ushort)
                //   +12: (4 bytes padding)
                //   +16: LogonDomainName.Buffer               (IntPtr)
                //   +24: UserName.Length                      (ushort)
                //   +26: UserName.MaximumLength               (ushort)
                //   +28: (4 bytes padding)
                //   +32: UserName.Buffer                      (IntPtr)
                //   +40: Password.Length                      (ushort)
                //   +42: Password.MaximumLength               (ushort)
                //   +44: (4 bytes padding)
                //   +48: Password.Buffer                      (IntPtr)
                //   +56: LUID (8 bytes)
                // Total header = 64 bytes

                Marshal.WriteInt32(buffer,  0, (int)KERB_LOGON_SUBMIT_TYPE.KerbWorkstationUnlockLogon);

                Marshal.WriteInt16(buffer,  8, (short)domainBytes.Length);
                Marshal.WriteInt16(buffer, 10, (short)domainBytes.Length);
                Marshal.WriteIntPtr(buffer, 16, IntPtr.Add(buffer, domainOffset));

                Marshal.WriteInt16(buffer, 24, (short)usernameBytes.Length);
                Marshal.WriteInt16(buffer, 26, (short)usernameBytes.Length);
                Marshal.WriteIntPtr(buffer, 32, IntPtr.Add(buffer, usernameOffset));

                Marshal.WriteInt16(buffer, 40, (short)passwordBytes.Length);
                Marshal.WriteInt16(buffer, 42, (short)passwordBytes.Length);
                Marshal.WriteIntPtr(buffer, 48, IntPtr.Add(buffer, passwordOffset));

                return new CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION
                {
                    ulAuthenticationPackage = _authPackageIndex,
                    clsidCredentialProvider = CredProvider.ProviderGuid,
                    cbSerialization         = (uint)totalSize,
                    rgbSerialization        = buffer,
                };
                // Note: do NOT free buffer here — Windows owns it after serialization
            }
            catch
            {
                Marshal.FreeCoTaskMem(buffer);
                throw;
            }
        }
    }

    // Helper: retrieve advise context from the events object when possible
    [ComImport]
    [Guid("e23ce12f-2a83-4ce3-b636-5285b643da88")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICredentialProviderCredentialEvents2 : ICredentialProviderCredentialEvents
    {
        IntPtr GetAdviseContext();
    }
}
