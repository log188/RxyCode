param(
  [Parameter(Mandatory = $true)][int]$ParentPid,
  [Parameter(Mandatory = $true)][int]$ChildPid
)

$src = @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

public static class WinJobGuard {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool SetInformationJobObject(IntPtr hJob, int JobObjectInfoClass, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);
  [DllImport("kernel32.dll", SetLastError = true)]
  private static extern bool CloseHandle(IntPtr hObject);

  [StructLayout(LayoutKind.Sequential)]
  private struct IO_COUNTERS {
    public ulong ReadOperationCount; public ulong WriteOperationCount; public ulong OtherOperationCount;
    public ulong ReadTransferCount; public ulong WriteTransferCount; public ulong OtherTransferCount;
  }
  [StructLayout(LayoutKind.Sequential)]
  private struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
    public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit;
    public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize;
    public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass;
  }
  [StructLayout(LayoutKind.Sequential)]
  private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
    public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
    public IO_COUNTERS IoInfo;
    public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit;
    public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed;
  }

  private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
  private const int JobObjectExtendedLimitInformation = 9;
  private const uint PROCESS_SET_QUOTA = 0x0100;
  private const uint PROCESS_TERMINATE = 0x0001;
  private const uint PROCESS_QUERY_INFORMATION = 0x0400;

  public static int Run(int parentPid, int childPid) {
    IntPtr job = CreateJobObject(IntPtr.Zero, null);
    if (job == IntPtr.Zero) return 1;
    var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    int size = Marshal.SizeOf(info);
    IntPtr ptr = Marshal.AllocHGlobal(size);
    bool limitSet = false;
    try {
      Marshal.StructureToPtr(info, ptr, false);
      limitSet = SetInformationJobObject(job, JobObjectExtendedLimitInformation, ptr, (uint)size);
    } finally {
      Marshal.FreeHGlobal(ptr);
    }
    if (!limitSet) return 2;

    IntPtr process = OpenProcess(
      PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION,
      false,
      childPid
    );
    if (process == IntPtr.Zero) return 3;
    bool assigned = AssignProcessToJobObject(job, process);
    CloseHandle(process);
    if (!assigned) return 4;

    while (true) {
      Thread.Sleep(300);
      bool parentAlive = IsAlive(parentPid);
      bool childAlive = IsAlive(childPid);
      if (!parentAlive || !childAlive) break;
    }
    return 0;
  }

  private static bool IsAlive(int pid) {
    try {
      using (var p = Process.GetProcessById(pid)) {
        return !p.HasExited;
      }
    } catch {
      return false;
    }
  }
}
'@

Add-Type -TypeDefinition $src
exit [WinJobGuard]::Run($ParentPid, $ChildPid)
