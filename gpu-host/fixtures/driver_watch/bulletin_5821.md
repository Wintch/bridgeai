### Security Bulletin: GPU Display Driver - May 2026

Updated 2026-05-21

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<div><span style="background-color: rgb(17, 22, 30);">To protect your system, download and install this software update through the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page or, for the vGPU software and Cloud Gaming updates, through the NVIDIA Licensing Portal.</span></div>

Go to [NVIDIA Product Security](https://www.nvidia.com/security/)

_______________________________________________________________________________________________________________________________________________

### Details

This section provides a summary of potential vulnerabilities that this security update addresses and their impact. Descriptions use [CWE™](https://cwe.mitre.org/), and base scores and vectors use [CVSS v3.1](https://www.first.org/cvss/specification-document) standards.

| **CVE ID** | **Description** | **Vector** | **Base Score** | **Severity** | **CWE** | **Impacts** |
| ---------- | ---------------- | ---------- | -------------- | ------------ | -------- | ------------ |
| CVE-2026-24187 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H) | 8.8 | HIGH | [CWE-416](https://cwe.mitre.org/data/definitions/416.html) | Denial of service, escalation of privileges, information disclosure, data tampering, code execution |
| CVE-2026-24190 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-862](https://cwe.mitre.org/data/definitions/862.html) | Denial of service, escalation of privileges, information disclosure, data tampering, code execution |

The NVIDIA risk assessment is based on an average of risk across a diverse set of installed systems and may not represent the true risk to your local installation. NVIDIA recommends evaluating the risk to your specific configuration.

### Security Updates

NVIDIA has released a software security update for NVIDIA GPU Display Driver to address the issues that are disclosed in this bulletin.<div>To protect your system, download and install this software update through the <a href="https://www.nvidia.com/Download/index.aspx">NVIDIA Driver Downloads</a> page or, for the vGPU software and Cloud Gaming updates, through the NVIDIA Licensing Portal.</div>

The following table lists the software products and versions affected, and the updated version available from nvidia.com that includes this security update.

| **CVE IDs Addressed** | **Affected Products** | **Platform or OS** | **Affected Versions** | **Updated Version** |
| --------------------- | --------------------- | ----------------- | --------------------- | ------------------- |
| CVE-2026-24187 | GeForce | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24187 | GeForce | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24187 | GeForce | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24187 | NVIDIA RTX, Quadro, NVS | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24187 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24187 | NVIDIA RTX, Quadro, NVS | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24187 | Tesla | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24187 | Tesla | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24187 | Tesla | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24187 | Guest driver | Linux(R595 vGPU 20) | 595.58.03(All versions prior to and including vGPU 20.0) | 595.71.05(vGPU 20.1) |
| CVE-2026-24187 | Guest driver | Linux(R580 vGPU 19) | 580.126.09(All versions prior to and including vGPU 19.4) | 580.159.03(vGPU 19.5) |
| CVE-2026-24187 | Guest driver | Linux(R535 vGPU 16) | 535.288.01(All versions prior to and including vGPU 16.13) | 535.309.01(vGPU 16.14) |
| CVE-2026-24187 | Guest driver | Linux(Cloud Gaming) | 595.58.03(All versions up to and including the March 2026 release) | 595.71.05(April 2026 Release) |
| CVE-2026-24187 | Virtual GPU Manager | Red Hat Enterprise Linux KVM, VMware vSphere(Cloud Gaming) | 595.58.02(All versions up to and including the March 2026 release) | 595.71.03(April 2026 Release) |
| CVE-2026-24187 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R595 vGPU 20) | 595.58.02(All versions prior to and including vGPU 20.0) | 595.71.03(vGPU 20.1) |
| CVE-2026-24187 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R580 vGPU 19) | 580.126.08(All versions prior to and including vGPU 19.4) | 580.159.01(vGPU 19.5) |
| CVE-2026-24187 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(R535 vGPU 16) | 535.288.01(All versions prior to and including vGPU 16.13) | 535.309.01(vGPU 16.14) |
| CVE-2026-24190 | GeForce | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24190 | GeForce | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24190 | GeForce | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24190 | Tesla | Linux(R595) | All driver versions prior to 595.71.05 | 595.71.05 |
| CVE-2026-24190 | Tesla | Linux(R580) | All driver versions prior to 580.159.03 | 580.159.03 |
| CVE-2026-24190 | Tesla | Linux(R535) | All driver versions prior to 535.309.01 | 535.309.01 |
| CVE-2026-24190 | GeForce | Windows(R595) | All driver versions prior to 596.36 | 596.36 |
| CVE-2026-24190 | GeForce | Windows(R580) | All driver versions prior to 582.53 Only GPUs based on the NVIDIA Maxwell, Volta, and Pascal GPU architectures are affected. | 582.53 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Windows(R595) | All driver versions prior to 596.36 | 596.36 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Windows(R580) | All driver versions prior to 582.53 | 582.53 |
| CVE-2026-24190 | NVIDIA RTX, Quadro, NVS | Windows(R535) | All driver versions prior to 539.72 | 539.72 |
| CVE-2026-24190 | Tesla | Windows(R595) | All driver versions prior to 596.36 | 596.36 |
| CVE-2026-24190 | Tesla | Windows(R580) | All driver versions prior to 582.53 | 582.53 |
| CVE-2026-24190 | Tesla | Windows(R535) | All driver versions prior to 539.72 | 539.72 |

### Notes
