// OneSign Windows Credential Provider
// PipeServer.cs — Named pipe listener that receives credentials from the agent
//
// The OneSign agent writes a 4-byte little-endian length-prefixed JSON message
// to \\.\pipe\OneSignCredProvider when it wants to unlock the workstation.
// This class starts a background thread that waits for exactly one message per
// pipe connection, parses it, and fires the CredentialsReceived event.

using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace OneSign.CredentialProvider
{
    /// <summary>
    /// Credentials delivered by the OneSign agent over the named pipe.
    /// </summary>
    internal sealed class AgentCredentials
    {
        public string Username { get; }
        public string Password { get; }
        public string Domain   { get; }

        public AgentCredentials(string username, string password, string domain)
        {
            Username = username;
            Password = password;
            Domain   = domain;
        }
    }

    /// <summary>
    /// Listens on \\.\pipe\OneSignCredProvider and raises CredentialsReceived
    /// each time the agent delivers a JSON credential blob.
    /// </summary>
    internal sealed class PipeServer : IDisposable
    {
        public const string PipeName = "OneSignCredProvider";

        public event EventHandler<AgentCredentials>? CredentialsReceived;

        private volatile bool _running;
        private Thread? _thread;

        public void Start()
        {
            if (_running) return;
            _running = true;
            _thread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name         = "OneSign-PipeServer",
            };
            _thread.Start();
        }

        public void Stop()
        {
            _running = false;
        }

        public void Dispose() => Stop();

        // ── Background listener ───────────────────────────────────────────────

        private void ListenLoop()
        {
            while (_running)
            {
                try
                {
                    using var pipe = new NamedPipeServerStream(
                        PipeName,
                        PipeDirection.In,
                        maxNumberOfServerInstances: 1,
                        PipeTransmissionMode.Byte,
                        PipeOptions.Asynchronous,
                        inBufferSize: 4096,
                        outBufferSize: 0
                    );

                    // Wait up to 5 seconds for a client; if no connection arrives
                    // loop again so we can check _running.
                    var connectTask = pipe.WaitForConnectionAsync();
                    if (!connectTask.Wait(5_000) || !_running)
                        continue;

                    using var reader = new BinaryReader(pipe, Encoding.UTF8, leaveOpen: true);

                    // Read 4-byte length prefix
                    int length = reader.ReadInt32();
                    if (length <= 0 || length > 65535)
                        continue;

                    byte[] buf = reader.ReadBytes(length);
                    if (buf.Length != length)
                        continue;

                    var creds = ParsePayload(buf);
                    if (creds != null)
                        CredentialsReceived?.Invoke(this, creds);
                }
                catch (IOException)
                {
                    // Client disconnected mid-read — loop again
                }
                catch (Exception)
                {
                    // Guard against unexpected errors; back off briefly
                    Thread.Sleep(1000);
                }
            }
        }

        private static AgentCredentials? ParsePayload(byte[] data)
        {
            try
            {
                var doc  = JsonDocument.Parse(data);
                var root = doc.RootElement;

                string username = root.GetProperty("username").GetString() ?? "";
                string password = root.GetProperty("password").GetString() ?? "";
                string domain   = root.TryGetProperty("domain", out var d)
                                    ? (d.GetString() ?? ".")
                                    : ".";

                if (string.IsNullOrEmpty(username))
                    return null;

                return new AgentCredentials(username, password, domain);
            }
            catch
            {
                return null;
            }
        }
    }
}
