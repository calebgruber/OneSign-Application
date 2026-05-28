// OneSign Windows Credential Provider
// CredProvider.cs — ICredentialProvider implementation + COM class factory
//
// GUID: {A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
// Register with Register.ps1; unregister with Unregister.ps1.
//
// The provider:
//   1. Starts PipeServer on SetUsageScenario (LOGON or UNLOCK)
//   2. Exposes a single CredentialTile
//   3. Delivers agent credentials to the tile and signals LogonUI

using System;
using System.Runtime.InteropServices;

namespace OneSign.CredentialProvider
{
    [ComVisible(true)]
    [Guid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890")]
    [ClassInterface(ClassInterfaceType.None)]
    [ProgId("OneSign.CredentialProvider")]
    public sealed class CredProvider : ICredentialProvider
    {
        // Must match the GUID above
        internal static readonly Guid ProviderGuid
            = new Guid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890");

        private PipeServer?      _pipeServer;
        private CredentialTile?  _tile;
        private ICredentialProviderEvents? _providerEvents;
        private IntPtr           _adviseContext;
        private uint             _authPackageIndex;

        // ── ICredentialProvider ───────────────────────────────────────────────

        public int SetUsageScenario(
            CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, uint dwFlags)
        {
            switch (cpus)
            {
                case CREDENTIAL_PROVIDER_USAGE_SCENARIO.CPUS_LOGON:
                case CREDENTIAL_PROVIDER_USAGE_SCENARIO.CPUS_UNLOCK_WORKSTATION:
                    _authPackageIndex = ResolveAuthPackage();
                    _tile = new CredentialTile(_authPackageIndex);

                    _pipeServer = new PipeServer();
                    _pipeServer.CredentialsReceived += OnCredentialsReceived;
                    _pipeServer.Start();
                    return 0; // S_OK

                default:
                    return unchecked((int)0x80004005); // E_FAIL — not supported
            }
        }

        public int SetSerialization(
            ref CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION pcpcs) => 0;

        public int Advise(ICredentialProviderEvents pcpe, IntPtr upAdviseContext)
        {
            _providerEvents = pcpe;
            _adviseContext  = upAdviseContext;
            return 0;
        }

        public int UnAdvise()
        {
            _pipeServer?.Stop();
            _pipeServer = null;
            _providerEvents = null;
            return 0;
        }

        public int GetFieldDescriptorCount(out uint pdwCount)
        {
            pdwCount = 4; // TILE_LABEL, STATUS_LABEL, PASSWORD, SUBMIT
            return 0;
        }

        public int GetFieldDescriptorAt(uint dwIndex, out IntPtr ppcpfd)
        {
            CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR desc;

            switch (dwIndex)
            {
                case CredentialTile.FIELD_TILE_LABEL:
                    desc = new CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR
                    {
                        dwFieldID    = CredentialTile.FIELD_TILE_LABEL,
                        cpft         = CREDENTIAL_PROVIDER_FIELD_TYPE.CPFT_LARGE_TEXT,
                        pszLabel     = "OneSign",
                        guidFieldType = Guid.Empty,
                    };
                    break;

                case CredentialTile.FIELD_STATUS_LABEL:
                    desc = new CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR
                    {
                        dwFieldID    = CredentialTile.FIELD_STATUS_LABEL,
                        cpft         = CREDENTIAL_PROVIDER_FIELD_TYPE.CPFT_SMALL_TEXT,
                        pszLabel     = "Status",
                        guidFieldType = Guid.Empty,
                    };
                    break;

                case CredentialTile.FIELD_PASSWORD:
                    desc = new CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR
                    {
                        dwFieldID    = CredentialTile.FIELD_PASSWORD,
                        cpft         = CREDENTIAL_PROVIDER_FIELD_TYPE.CPFT_PASSWORD_TEXT,
                        pszLabel     = "Password",
                        guidFieldType = Guid.Empty,
                    };
                    break;

                case CredentialTile.FIELD_SUBMIT:
                    desc = new CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR
                    {
                        dwFieldID    = CredentialTile.FIELD_SUBMIT,
                        cpft         = CREDENTIAL_PROVIDER_FIELD_TYPE.CPFT_SUBMIT_BUTTON,
                        pszLabel     = "Sign In",
                        guidFieldType = Guid.Empty,
                    };
                    break;

                default:
                    ppcpfd = IntPtr.Zero;
                    return unchecked((int)0x80070057); // E_INVALIDARG
            }

            // Allocate and return a copy on the COM heap
            ppcpfd = Marshal.AllocCoTaskMem(
                Marshal.SizeOf<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR>());
            Marshal.StructureToPtr(desc, ppcpfd, false);
            return 0;
        }

        public int GetCredentialCount(
            out uint pdwCount,
            out uint pdwDefault,
            out bool pbAutoLogonWithDefault)
        {
            pdwCount              = 1;
            pdwDefault            = 0;
            pbAutoLogonWithDefault = false;
            return 0;
        }

        public int GetCredentialAt(uint dwIndex,
            out ICredentialProviderCredential ppcpc)
        {
            if (dwIndex == 0 && _tile != null)
            {
                ppcpc = _tile;
                return 0;
            }
            ppcpc = null!;
            return unchecked((int)0x80070057);
        }

        // ── Pipe event handler ────────────────────────────────────────────────

        private void OnCredentialsReceived(object? sender, AgentCredentials creds)
        {
            _tile?.DeliverCredentials(creds);
        }

        // ── Auth package resolution ───────────────────────────────────────────

        [DllImport("secur32.dll", SetLastError = false)]
        private static extern int LsaConnectUntrusted(out IntPtr LsaHandle);

        [DllImport("secur32.dll", SetLastError = false)]
        private static extern int LsaLookupAuthenticationPackage(
            IntPtr LsaHandle,
            ref LSA_STRING PackageName,
            out uint AuthenticationPackage);

        [DllImport("secur32.dll", SetLastError = false)]
        private static extern int LsaDeregisterLogonProcess(IntPtr LsaHandle);

        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_STRING
        {
            public ushort Length;
            public ushort MaximumLength;
            public IntPtr Buffer;
        }

        private static uint ResolveAuthPackage()
        {
            LsaConnectUntrusted(out IntPtr lsa);
            try
            {
                const string packageName = "Kerberos";
                IntPtr namePtr = Marshal.StringToHGlobalAnsi(packageName);
                try
                {
                    var lsaStr = new LSA_STRING
                    {
                        Length        = (ushort)packageName.Length,
                        MaximumLength = (ushort)(packageName.Length + 1),
                        Buffer        = namePtr,
                    };
                    LsaLookupAuthenticationPackage(lsa, ref lsaStr, out uint pkgIndex);
                    return pkgIndex;
                }
                finally
                {
                    Marshal.FreeHGlobal(namePtr);
                }
            }
            finally
            {
                LsaDeregisterLogonProcess(lsa);
            }
        }
    }
}
