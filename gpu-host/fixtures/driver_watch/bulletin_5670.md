### Security Bulletin: GPU Display Driver - July 2025

Updated 2025-07-24

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<br>To protect your system, download and install this software update through the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page or, for the vGPU software and Cloud Gaming updates, through the <a href="https://www.nvidia.com/content/nvidia/en-us/cloud-gaming/cloud-gaming-downloads.html">NVIDIA Licensing Portal</a>.

Go to [NVIDIA Product Security](https://www.nvidia.com/security/)

_______________________________________________________________________________________________________________________________________________

### Details

This section provides a summary of potential vulnerabilities that this security update addresses and their impact. Descriptions use [CWE™](https://cwe.mitre.org/), and base scores and vectors use [CVSS v3.1](https://www.first.org/cvss/specification-document) standards.

| **CVE ID** | **Description** | **Vector** | **Base Score** | **Severity** | **CWE** | **Impacts** |
| ---------- | ---------------- | ---------- | -------------- | ------------ | -------- | ------------ |
| CVE-2025-23276 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-552](https://cwe.mitre.org/data/definitions/552.html) | Code Execution, Escalation of Privileges, Data Tampering, Information Disclosure, Denial of Service |
| CVE-2025-23283 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-121](https://cwe.mitre.org/data/definitions/121.html) | Code Execution, Denial of Service, Escalation of Privileges, Information Disclosure, Data Tampering |

The NVIDIA risk assessment is based on an average of risk across a diverse set of installed systems and may not represent the true risk to your local installation. NVIDIA recommends evaluating the risk to your specific configuration.

### Security Updates

The following table lists the NVIDIA software products affected, display driver versions affected, and the updated version available from nvidia.com that includes this security update. Download the updates from the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page.

The following table lists the software products and versions affected, and the updated version available from nvidia.com that includes this security update.

| **CVE IDs Addressed** | **Affected Products** | **Platform or OS** | **Affected Versions** | **Updated Version** |
| --------------------- | --------------------- | ----------------- | --------------------- | ------------------- |
| CVE-2025-23276 | GeForce | Windows(R575) | All driver versions prior to 577.00 | 577.00 |
| CVE-2025-23276 | NVIDIA RTX, Quadro, NVS | Windows(R570) | All driver versions prior to 573.48 | 573.48 |
| CVE-2025-23276 | NVIDIA RTX, Quadro, NVS | Windows(R535) | All driver versions prior to 539.41 | 539.41 |
| CVE-2025-23276 | Tesla | Windows(R570) | All driver versions prior to 573.48 | 573.48 |
| CVE-2025-23276 | Tesla | Windows(R535) | All driver versions prior to 539.41 | 539.41 |
| CVE-2025-23279 | Virtual GPU Manager | Red Hat Enterprise Linux KVM(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23279 | Virtual GPU Manager | Ubuntu(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23279 | Virtual GPU Manager | Red Hat Enterprise Linux KVM(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23279 | Virtual GPU Manager | Ubuntu(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23279 | Virtual GPU Manager | Citrix Hypervisor(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23279 | Virtual GPU Manager | Citrix Hypervisor(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23279 | Virtual GPU Manager | VMware vSphere(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23279 | Virtual GPU Manager | VMware vSphere(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23279 | Guest driver | Linux(R570 vGPU 18) | 570.158.01(All versions prior to and including vGPU 18.3) | 570.172.08(vGPU 18.4) |
| CVE-2025-23279 | Guest driver | Linux(R535 vGPU 16) | 535.247.01(All versions prior to and including vGPU 16.10) | 535.261.03(vGPU 16.11) |
| CVE-2025-23279 | GeForce | Linux(R570) | All driver version prior to 570.172.08 | 570.172.08 |
| CVE-2025-23279 | NVIDIA RTX, Quadro, NVS | Linux(R570) | All driver version prior to 570.172.08 | 570.172.08 |
| CVE-2025-23279 | Tesla | Linux(R570) | All driver version prior to 570.172.08 | 570.172.08 |
| CVE-2025-23286 | GeForce | Windows(R575) | All driver versions prior to 577.00 | 577.00 |
| CVE-2025-23286 | NVIDIA RTX, Quadro, NVS | Windows(R570) | All driver versions prior to 573.48 | 573.48 |
| CVE-2025-23286 | NVIDIA RTX, Quadro, NVS | Windows(R535) | All driver versions prior to 539.41 | 539.41 |
| CVE-2025-23286 | Tesla | Windows(R570) | All driver versions prior to 573.48 | 573.48 |
| CVE-2025-23286 | Tesla | Windows(R535) | All driver versions prior to 539.41 | 539.41 |
| CVE-2025-23286 | Virtual GPU Manager | Red Hat Enterprise Linux KVM(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23286 | Virtual GPU Manager | Ubuntu(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23286 | Virtual GPU Manager | Red Hat Enterprise Linux KVM(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23286 | Virtual GPU Manager | Ubuntu(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23286 | Virtual GPU Manager | Azure Stack HCI(R535 vGPU 18) | 539.28(All versions prior to and including vGPU 18.3) | 573.55(vGPU 18.4) |
| CVE-2025-23286 | Virtual GPU Manager | Citrix Hypervisor(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23286 | Virtual GPU Manager | Citrix Hypervisor(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23286 | Virtual GPU Manager | VMware vSphere(R570 vGPU 18) | 570.158.02(All versions prior to and including vGPU 18.3) | 570.172.07(vGPU 18.4) |
| CVE-2025-23286 | Virtual GPU Manager | VMware vSphere(R535 vGPU 16) | 535.247.02(All versions prior to and including vGPU 16.10) | 535.261.04(vGPU 16.11) |
| CVE-2025-23286 | GeForce | Linux(R535) | All driver versions prior to 535.261.03 | 535.261.03 |
| CVE-2025-23286 | NVIDIA RTX, Quadro, NVS | Linux(R535) | All driver versions prior to 535.261.03 | 535.261.03 |
| CVE-2025-23286 | Tesla | Linux(R535) | All driver versions prior to 535.261.03 | 535.261.03 |

### Notes
