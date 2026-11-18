### Security Bulletin: NVIDIA GPU Display Driver - October 2025

Updated 2025-10-09

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<br>To protect your system, download and install this software update through the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page or, for the vGPU software and Cloud Gaming updates, through the <a href="https://www.nvidia.com/content/nvidia/en-us/cloud-gaming/cloud-gaming-downloads.html">NVIDIA Licensing Portal</a>.

Go to [NVIDIA Product Security](https://www.nvidia.com/security/)

_______________________________________________________________________________________________________________________________________________

### Details

This section provides a summary of potential vulnerabilities that this security update addresses and their impact. Descriptions use [CWE™](https://cwe.mitre.org/), and base scores and vectors use [CVSS v3.1](https://www.first.org/cvss/specification-document) standards.

| **CVE ID** | **Description** | **Vector** | **Base Score** | **Severity** | **CWE** | **Impacts** |
| ---------- | ---------------- | ---------- | -------------- | ------------ | -------- | ------------ |
| CVE-2025-23309 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:H) | 8.2 | HIGH | [CWE-427](https://cwe.mitre.org/data/definitions/427.html) | Denial of Service, Escalation of Privileges, Data Tampering |
| CVE-2025-23347 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-276](https://cwe.mitre.org/data/definitions/276.html) | Code Execution, Escalation of Privileges, Data Tampering, Information Disclosure, Denial of Service |

The NVIDIA risk assessment is based on an average of risk across a diverse set of installed systems and may not represent the true risk to your local installation. NVIDIA recommends evaluating the risk to your specific configuration.

### Security Updates

The following table lists the NVIDIA software products affected, display driver versions affected, and the updated version available from nvidia.com that includes this security update. Download the updates from the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page.

The following table lists the software products and versions affected, and the updated version available from nvidia.com that includes this security update.

| **CVE IDs Addressed** | **Affected Products** | **Platform or OS** | **Affected Versions** | **Updated Version** |
| --------------------- | --------------------- | ----------------- | --------------------- | ------------------- |
| CVE-2025-23309 | GeForce | Windows(R580) | All driver versions prior to 581.42 | 581.42 |
| CVE-2025-23309 | NVIDIA RTX, Quadro, NVS | Windows(R580) | All driver versions prior to 581.42 | 581.42 |
| CVE-2025-23309 | NVIDIA RTX, Quadro, NVS | Windows(R570) | All driver versions prior to 573.76 | 573.76 |
| CVE-2025-23309 | NVIDIA RTX, Quadro, NVS | Windows(R535) | All driver versions prior to 539.56 | 539.56 |
| CVE-2025-23309 | Tesla | Windows(R580) | All driver versions prior to 581.42 | 581.42 |
| CVE-2025-23309 | Tesla | Windows(R570) | All driver versions prior to 573.76 | 573.76 |
| CVE-2025-23309 | Tesla | Windows(R535) | All driver versions prior to 539.56 | 539.56 |
| CVE-2025-23280 | GeForce | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23280 | GeForce | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23280 | GeForce | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23280 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23280 | NVIDIA RTX, Quadro, NVS | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23280 | NVIDIA RTX, Quadro, NVS | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23280 | Tesla | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23280 | Tesla | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23280 | Tesla | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23280 | Guest driver | Linux(R580 vGPU 19) | 580.82.07(All versions prior to and including vGPU 19.1) | 580.95.05(vGPU 19.2) |
| CVE-2025-23280 | Guest driver | Linux(R580 Gaming) | 580.82.07(All versions up to and including the August 2025 release) | 580.95.05(September 2025 Release) |
| CVE-2025-23280 | Guest driver | Linux(R570 vGPU 18) | 570.172.08(All versions prior to and including vGPU 18.4) | 570.195.03(vGPU 18.5) |
| CVE-2025-23280 | Guest driver | Linux(R535 vGPU 16) | 535.261.03(All versions prior to and including vGPU 16.11) | 575.274.02(vGPU 16.12) |
| CVE-2025-23282 | Virtual GPU Manager | Red Hat Enterprise Linux KVM, VMware vSphere(R580 Gaming) | 580.82.02(All versions up to and including the August 2025 release) | 580.95.02(September 2025 Release) |
| CVE-2025-23282 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R580 vGPU 19) | 580.82.02(All versions prior to and including vGPU 19.1) | 580.95.02(vGPU 19.2) |
| CVE-2025-23282 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R570 vGPU 18) | 570.172.07(All versions prior to and including vGPU 18.4) | 570.195.02(vGPU 18.5) |
| CVE-2025-23282 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R535 vGPU 16) | 535.261.04(All versions prior to and including vGPU 16.11) | 575.274.03(vGPU 16.12) |
| CVE-2025-23282 | GeForce | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23282 | GeForce | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23282 | GeForce | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23282 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23282 | NVIDIA RTX, Quadro, NVS | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23282 | NVIDIA RTX, Quadro, NVS | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23282 | Tesla | Linux(R580) | All driver versions prior to 580.95.05 | 580.95.05 |
| CVE-2025-23282 | Tesla | Linux(R570) | All driver versions prior to 570.195.03 | 570.195.03 |
| CVE-2025-23282 | Tesla | Linux(R535) | All driver versions prior to 535.274.02 | 535.274.02 |
| CVE-2025-23282 | Guest driver | Linux(R580 vGPU 19) | 580.82.07(All versions prior to and including vGPU 19.1) | 580.95.05(vGPU 19.2) |
| CVE-2025-23282 | Guest driver | Linux(R580 Gaming) | 580.82.07(All versions up to and including the August 2025 release) | 580.95.05(September 2025 Release) |
| CVE-2025-23282 | Guest driver | Linux(R570 vGPU 18) | 570.172.08(All versions prior to and including vGPU 18.4) | 570.195.03(vGPU 18.5) |
| CVE-2025-23282 | Guest driver | Linux(R535 vGPU 16) | 535.261.03(All versions prior to and including vGPU 16.11) | 575.274.02(vGPU 16.12) |

### Notes
