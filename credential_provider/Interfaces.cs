// OneSign Windows Credential Provider
// Interfaces.cs — COM interface declarations with correct vtable ordering
//
// These interfaces mirror the Windows SDK COM definitions.  We declare them
// in C# with the exact vtable slots required by LogonUI/Winlogon so that
// the .NET COM-callable wrapper (CCW) exposes the correct binary layout.

using System;
using System.Runtime.InteropServices;

namespace OneSign.CredentialProvider
{
    // ── Supporting types ─────────────────────────────────────────────────────

    [StructLayout(LayoutKind.Sequential)]
    internal struct KERB_INTERACTIVE_UNLOCK_LOGON
    {
        public KERB_INTERACTIVE_LOGON Logon;
        public LUID LogonId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct KERB_INTERACTIVE_LOGON
    {
        public KERB_LOGON_SUBMIT_TYPE MessageType;
        public UNICODE_STRING LogonDomainName;
        public UNICODE_STRING UserName;
        public UNICODE_STRING Password;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct UNICODE_STRING
    {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct LUID
    {
        public uint LowPart;
        public int  HighPart;
    }

    internal enum KERB_LOGON_SUBMIT_TYPE
    {
        KerbInteractiveLogon            = 2,
        KerbWorkstationUnlockLogon      = 7,
        KerbS4ULogon                    = 12,
        KerbCertificateUnlockLogon      = 18,
    }

    internal enum CREDENTIAL_PROVIDER_USAGE_SCENARIO
    {
        CPUS_INVALID            = 0,
        CPUS_LOGON              = 1,
        CPUS_UNLOCK_WORKSTATION = 2,
        CPUS_CHANGE_PASSWORD    = 3,
        CPUS_CREDUI             = 4,
        CPUS_PLAP               = 5,
    }

    internal enum CREDENTIAL_PROVIDER_FIELD_TYPE
    {
        CPFT_INVALID              = 0,
        CPFT_LARGE_TEXT           = 1,
        CPFT_SMALL_TEXT           = 2,
        CPFT_COMMAND_LINK         = 3,
        CPFT_EDIT_TEXT            = 4,
        CPFT_PASSWORD_TEXT        = 5,
        CPFT_TILE_IMAGE           = 6,
        CPFT_CHECKBOX             = 7,
        CPFT_COMBOBOX             = 8,
        CPFT_SUBMIT_BUTTON        = 9,
    }

    internal enum CREDENTIAL_PROVIDER_FIELD_STATE
    {
        CPFS_HIDDEN               = 0,
        CPFS_DISPLAY_IN_SELECTED_TILE   = 1,
        CPFS_DISPLAY_IN_DESELECTED_TILE = 2,
        CPFS_DISPLAY_IN_BOTH            = 3,
    }

    internal enum CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE
    {
        CPFIS_NONE      = 0,
        CPFIS_READONLY  = 1,
        CPFIS_DISABLED  = 2,
        CPFIS_FOCUSED   = 3,
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR
    {
        public uint  dwFieldID;
        public CREDENTIAL_PROVIDER_FIELD_TYPE cpft;
        [MarshalAs(UnmanagedType.LPWStr)]
        public string? pszLabel;
        public Guid guidFieldType;
    }

    internal enum NTSTATUS : uint
    {
        STATUS_SUCCESS              = 0x00000000,
        STATUS_NOT_IMPLEMENTED      = 0xC0000002,
        STATUS_INVALID_INFO_CLASS   = 0xC0000003,
    }

    internal enum CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE
    {
        CPGSR_NO_CREDENTIAL_NOT_FINISHED  = 0,
        CPGSR_NO_CREDENTIAL_FINISHED      = 1,
        CPGSR_RETURN_CREDENTIAL_FINISHED  = 2,
        CPGSR_RETURN_NO_CREDENTIAL_FINISHED = 3,
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION
    {
        public uint ulAuthenticationPackage;
        public Guid clsidCredentialProvider;
        public uint cbSerialization;
        public IntPtr rgbSerialization;
    }

    // ── ICredentialProvider ───────────────────────────────────────────────────

    [ComImport]
    [Guid("d545db01-e522-4a63-af83-d8ddf954004d")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICredentialProvider
    {
        [PreserveSig] int SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, uint dwFlags);
        [PreserveSig] int SetSerialization(ref CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION pcpcs);
        [PreserveSig] int Advise(ICredentialProviderEvents pcpe, [MarshalAs(UnmanagedType.SysUInt)] IntPtr upAdviseContext);
        [PreserveSig] int UnAdvise();
        [PreserveSig] int GetFieldDescriptorCount(out uint pdwCount);
        [PreserveSig] int GetFieldDescriptorAt(uint dwIndex, out IntPtr ppcpfd);
        [PreserveSig] int GetCredentialCount(out uint pdwCount, out uint pdwDefault, [MarshalAs(UnmanagedType.Bool)] out bool pbAutoLogonWithDefault);
        [PreserveSig] int GetCredentialAt(uint dwIndex, out ICredentialProviderCredential ppcpc);
    }

    // ── ICredentialProviderEvents ─────────────────────────────────────────────

    [ComImport]
    [Guid("b63b6cb8-1d68-49ea-8b2e-6c34343fc37b")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICredentialProviderEvents
    {
        [PreserveSig] int CredentialsChanged([MarshalAs(UnmanagedType.SysUInt)] IntPtr upAdviseContext);
    }

    // ── ICredentialProviderCredential ─────────────────────────────────────────

    [ComImport]
    [Guid("63913a93-40c1-481a-818d-4072ff8c70cc")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICredentialProviderCredential
    {
        [PreserveSig] int Advise(ICredentialProviderCredentialEvents pcpce);
        [PreserveSig] int UnAdvise();
        [PreserveSig] int SetSelected([MarshalAs(UnmanagedType.Bool)] out bool pbAutoLogon);
        [PreserveSig] int SetDeselected();
        [PreserveSig] int GetFieldState(uint dwFieldID, out CREDENTIAL_PROVIDER_FIELD_STATE pcpfs, out CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE pcpfis);
        [PreserveSig] int GetStringValue(uint dwFieldID, [MarshalAs(UnmanagedType.LPWStr)] out string? ppsz);
        [PreserveSig] int GetBitmapValue(uint dwFieldID, out IntPtr phbmp);
        [PreserveSig] int GetCheckboxValue(uint dwFieldID, [MarshalAs(UnmanagedType.Bool)] out bool pbChecked, [MarshalAs(UnmanagedType.LPWStr)] out string? ppszLabel);
        [PreserveSig] int GetSubmitButtonValue(uint dwFieldID, out uint pdwAdjacentTo);
        [PreserveSig] int GetComboBoxValueCount(uint dwFieldID, out uint pcItems, out uint pdwSelectedItem);
        [PreserveSig] int GetComboBoxValueAt(uint dwFieldID, uint dwItem, [MarshalAs(UnmanagedType.LPWStr)] out string? ppszItem);
        [PreserveSig] int SetStringValue(uint dwFieldID, [MarshalAs(UnmanagedType.LPWStr)] string psz);
        [PreserveSig] int SetCheckboxValue(uint dwFieldID, [MarshalAs(UnmanagedType.Bool)] bool bChecked);
        [PreserveSig] int SetComboBoxSelectedValue(uint dwFieldID, uint dwSelectedItem);
        [PreserveSig] int CommandLinkClicked(uint dwFieldID);
        [PreserveSig] int GetSerialization(out CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE pcpgsr, out CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION pcpcs, [MarshalAs(UnmanagedType.LPWStr)] out string? ppszOptionalStatusText, out uint pcpsiOptionalStatusIcon);
        [PreserveSig] int ReportResult(int ntsStatus, int ntsSubstatus, [MarshalAs(UnmanagedType.LPWStr)] out string? ppszOptionalStatusText, out uint pcpsiOptionalStatusIcon);
    }

    // ── ICredentialProviderCredentialEvents ───────────────────────────────────

    [ComImport]
    [Guid("dbc6fb30-c843-49e3-a645-573e6f39446a")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICredentialProviderCredentialEvents
    {
        [PreserveSig] int SetFieldState(ICredentialProviderCredential pcpc, uint dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE cpfs);
        [PreserveSig] int SetFieldInteractiveState(ICredentialProviderCredential pcpc, uint dwFieldID, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE cpfis);
        [PreserveSig] int SetFieldString(ICredentialProviderCredential pcpc, uint dwFieldID, [MarshalAs(UnmanagedType.LPWStr)] string psz);
        [PreserveSig] int SetFieldCheckbox(ICredentialProviderCredential pcpc, uint dwFieldID, [MarshalAs(UnmanagedType.Bool)] bool bChecked, [MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
        [PreserveSig] int SetFieldBitmap(ICredentialProviderCredential pcpc, uint dwFieldID, IntPtr hbmp);
        [PreserveSig] int SetFieldComboBoxSelectedItem(ICredentialProviderCredential pcpc, uint dwFieldID, uint dwSelectedItem);
        [PreserveSig] int DeleteFieldComboBoxItem(ICredentialProviderCredential pcpc, uint dwFieldID, uint dwItem);
        [PreserveSig] int AppendFieldComboBoxItem(ICredentialProviderCredential pcpc, uint dwFieldID, [MarshalAs(UnmanagedType.LPWStr)] string pszItem);
        [PreserveSig] int SetFieldSubmitButton(ICredentialProviderCredential pcpc, uint dwFieldID, uint dwAdjacentTo);
        [PreserveSig] int OnCreatingWindow(out IntPtr phwndOwner);
    }
}
