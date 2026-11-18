### Security Bulletin: GPU Display Driver – September 2026

Updated 2026-10-13

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<div>To protect your system, download and install this software update through the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page or, for the vGPU software and Cloud Gaming updates, through the <a href="https://www.nvidia.com/content/nvidia/en-us/cloud-gaming/cloud-gaming-downloads.html">NVIDIA Licensing Portal</a>.</div>

Go to [NVIDIA Product Security](https://www.nvidia.com/security/)

_______________________________________________________________________________________________________________________________________________

### Details

This section provides a summary of potential vulnerabilities that this security update addresses and their impact. Descriptions use [CWE&trade;](https://cwe.mitre.org/), and base scores and vectors use [CVSS v3.1](https://www.first.org/cvss/specification-document) standards.

| **CVE ID** | **Description** | **Vector** | **Base Score** | **Severity** | **CWE** | **Impacts** |
| ---------- | ---------------- | ---------- | -------------- | ------------ | -------- | ------------ |
| CVE-2026-47601 | (description left out of the fixture) | [CVSS:3.1<br>/AV:L<br>/AC:L<br>/PR:L<br>/UI:N<br>/S:U<br>/C:H<br>/I:H<br>/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-787](https://cwe.mitre.org/data/definitions/787.html) | Code execution, escalation of privileges, data tampering, denial of service, information disclosure |
| CVE-2026-47600 | (description left out of the fixture) | [CVSS:3.1<br>/AV:L<br>/AC:L<br>/PR:L<br>/UI:N<br>/S:U<br>/C:H<br>/I:H<br>/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-908](https://cwe.mitre.org/data/definitions/908.html) | Code execution, escalation of privileges, data tampering, denial of service, information disclosure |

The NVIDIA risk assessment is based on an average of risk across a diverse set of installed systems and might not represent the true risk to your local installation. NVIDIA recommends evaluating the risk to your specific configuration.

### Security Updates

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<div><span style="color: var(--text-color-primary); font-family:  (long paragraph left out of the fixture)

The following table lists the software products and versions affected, and the updated version available from nvidia.com that includes this security update.

| **CVE Addressed** | **Affected Products** | **Platform or OS** | **Affected Versions** | **Updated Version** |
| --------------------- | --------------------- | ----------------- | --------------------- | ------------------- |
| CVE-2026-47604 | GeForce | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47604 | GeForce | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47604 | GeForce | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47604 | Guest driver | Linux(vGPU 19) | 580.159.03(All versions prior to and including vGPU 19.5) | 580.178.04(vGPU 19.6) |
| CVE-2026-47604 | Guest driver | Linux(vGPU 20) | 595.71.05(All versions prior to and including vGPU 20.1) | 595.91.07(vGPU 20.2) |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47604 | Tesla | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47604 | Tesla | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47604 | Tesla | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47604 | Tesla | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47604 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 19) | 580.159.01(All versions prior to and including vGPU 19.5) | 580.178.05(vGPU 19.6) |
| CVE-2026-47604 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 20) | 595.71.03(All versions prior to and including vGPU 20.1) | 595.91.04(vGPU 20.2) |
| CVE-2026-47604 | GeForce | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47604 | GeForce | Windows(R580) | All driver versions prior to 582.78 Only GPUs based on the NVIDIA Maxwell, Volta, and Pascal GPU architectures are affected. | 582.78 |
| CVE-2026-47604 | GeForce | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47604 | GeForce | Windows(R615) | All driver versions prior to 616.56 | 616.56 |
| CVE-2026-47604 | Guest driver | Windows(vGPU 19) | 582.53(All versions prior to and including vGPU 19.5) | 582.78(vGPU 19.6) |
| CVE-2026-47604 | Guest driver | Windows(vGPU 20) | 596.36(All versions prior to and including vGPU 20.1) | 596.86(vGPU 20.2) |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Windows(R580) | All driver versions prior to 582.78 | 582.78 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Windows(R595) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47604 | NVIDIA RTX, Quadro, NVS | Windows(R615) | All driver versions prior to  616.92 | 616.92 |
| CVE-2026-47604 | Tesla | Windows(R580) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47604 | Tesla | Windows(R595) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47604 | Tesla | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47604 | Tesla | Windows(R615) | All driver versions prior to 616.92 | 616.92 |
| CVE-2026-47604 | Virtual GPU Manager | Azure Local, Windows Server(vGPU 19) | 582.51(All versions prior to and including vGPU 19.5) | 582.78(vGPU 19.6) |
| CVE-2026-47604 | Virtual GPU Manager | Azure Local, Windows Server(vGPU 20) | 596.38(All versions prior to and including vGPU 20.1) | 596.84(vGPU 20.2) |
| CVE-2026-47603 | GeForce | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47603 | GeForce | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47603 | GeForce | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47603 | Guest driver | Linux(vGPU 19) | 580.159.03(All versions prior to and including vGPU 19.5) | 580.178.04(vGPU 19.6) |
| CVE-2026-47603 | Guest driver | Linux(vGPU 20) | 595.71.05(All versions prior to and including vGPU 20.1) | 595.91.07(vGPU 20.2) |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47603 | Tesla | Linux(R580) | All driver versions prior to 580.178.04 | 580.178.04 |
| CVE-2026-47603 | Tesla | Linux(R595) | All driver versions prior to 595.91.07 | 595.91.07 |
| CVE-2026-47603 | Tesla | Linux(R610) | All driver versions prior to 610.57.04 | 610.57.04 |
| CVE-2026-47603 | Tesla | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47603 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 19) | 580.159.01(All versions prior to and including vGPU 19.5) | 580.178.05(vGPU 19.6) |
| CVE-2026-47603 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 20) | 595.71.03(All versions prior to and including vGPU 20.1) | 595.91.04(vGPU 20.2) |
| CVE-2026-47603 | GeForce | Linux(R615) | All driver versions prior to 615.71.09 | 615.71.09 |
| CVE-2026-47603 | GeForce | Windows(R580) | All driver versions prior to 582.78 Only GPUs based on the NVIDIA Maxwell, Volta, and Pascal GPU architectures are affected. | 582.78 |
| CVE-2026-47603 | GeForce | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47603 | GeForce | Windows(R615) | All driver versions prior to 616.56 | 616.56 |
| CVE-2026-47603 | Guest driver | Windows(vGPU 19) | 582.53(All versions prior to and including vGPU 19.5) | 582.78(vGPU 19.6) |
| CVE-2026-47603 | Guest driver | Windows(vGPU 20) | 596.36(All versions prior to and including vGPU 20.1) | 596.86(vGPU 20.2) |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Windows(R580) | All driver versions prior to 582.78 | 582.78 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Windows(R595) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47603 | NVIDIA RTX, Quadro, NVS | Windows(R615) | All driver versions prior to  616.92 | 616.92 |
| CVE-2026-47603 | Tesla | Windows(R580) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47603 | Tesla | Windows(R595) | All driver versions prior to 596.86 | 596.86 |
| CVE-2026-47603 | Tesla | Windows(R610) | All driver versions prior to 610.88 | 610.88 |
| CVE-2026-47603 | Tesla | Windows(R615) | All driver versions prior to 616.92 | 616.92 |
| CVE-2026-47603 | Virtual GPU Manager | Azure Local, Windows Server(vGPU 19) | 582.51(All versions prior to and including vGPU 19.5) | 582.78(vGPU 19.6) |
| CVE-2026-47603 | Virtual GPU Manager | Azure Local, Windows Server(vGPU 20) | 596.38(All versions prior to and including vGPU 20.1) | 596.84(vGPU 20.2) |

### Notes
