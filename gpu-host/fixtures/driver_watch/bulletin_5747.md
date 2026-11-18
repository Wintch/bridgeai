### Security Bulletin: GPU Display Driver - January 2026

Updated 2026-01-28

NVIDIA has released security updates to address vulnerabilities in various products.

Go to [NVIDIA Product Security](https://www.nvidia.com/security/)

_______________________________________________________________________________________________________________________________________________

### Details

This section provides a summary of potential vulnerabilities that this security update addresses and their impact. Descriptions use [CWE™](https://cwe.mitre.org/), and base scores and vectors use [CVSS v3.1](https://www.first.org/cvss/specification-document) standards.

| **CVE ID** | **Description** | **Vector** | **Base Score** | **Severity** | **CWE** | **Impacts** |
| ---------- | ---------------- | ---------- | -------------- | ------------ | -------- | ------------ |
| CVE-2025-33217 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-416](https://cwe.mitre.org/data/definitions/416.html) | Code execution, escalation of privileges, data tampering, denial of service, information disclosure |
| CVE-2025-33218 | (description left out of the fixture) | [CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H](https://www.first.org/cvss/calculator/3.1#CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) | 7.8 | HIGH | [CWE-190](https://cwe.mitre.org/data/definitions/190.html) | Code execution, escalation of privileges, data tampering, denial of service, information disclosure |

The NVIDIA risk assessment is based on an average of risk across a diverse set of installed systems and may not represent the true risk to your local installation. NVIDIA recommends evaluating the risk to your specific configuration.

### Security Updates

<ul><li>Your computer hardware vendor might provide you with Windows GPU display driver versions including 591.55, 581.95, 573.91, and 539.61, which also contain the security updates</li><li>The table (long paragraph left out of the fixture)

The following table lists the software products and versions affected, and the updated version available from nvidia.com that includes this security update.

| **CVE IDs Addressed** | **Affected Products** | **Platform or OS** | **Affected Versions** | **Updated Version** |
| --------------------- | --------------------- | ----------------- | --------------------- | ------------------- |
| CVE-2025-33217 | GeForce | Windows(R590) | All driver versions prior to 591.59 | 591.59 |
| CVE-2025-33217 | NVIDIA RTX PRO, RTX, Quadro | Windows(R590) | All driver versions prior to 591.59 | 591.59 |
| CVE-2025-33217 | NVIDIA RTX PRO, RTX, Quadro | Windows(R580) | All driver versions prior to 582.16 | 582.16 |
| CVE-2025-33217 | NVIDIA RTX PRO, RTX, Quadro | Windows(R570) | All driver versions prior to 573.96 | 573.96 |
| CVE-2025-33217 | NVIDIA RTX PRO, RTX, Quadro | Windows(R535) | All driver versions prior to 539.64 | 539.64 |
| CVE-2025-33217 | Tesla | Windows(R590) | All driver versions prior to 591.59 | 591.59 |
| CVE-2025-33217 | Tesla | Windows(R580) | All driver versions prior to 582.16 | 582.16 |
| CVE-2025-33217 | Tesla | Windows(R570) | All driver versions prior to 573.96 | 573.96 |
| CVE-2025-33217 | Tesla | Windows(R535) | All driver versions prior to 539.64 | 539.64 |
| CVE-2025-33219 | GeForce | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33219 | GeForce | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33219 | GeForce | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33219 | GeForce | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33219 | NVIDIA RTX PRO, RTX, Quadro | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33219 | NVIDIA RTX PRO, RTX, Quadro | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33219 | NVIDIA RTX PRO, RTX, Quadro | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33219 | NVIDIA RTX PRO, RTX, Quadro | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33219 | Tesla | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33219 | Tesla | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33219 | Tesla | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33219 | Tesla | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33219 | Guest driver | Linux(R580 vGPU 19) | 580.105.08(All versions prior to and including vGPU software 19.3) | 580.126.09(vGPU software 19.4) |
| CVE-2025-33219 | Guest driver | Linux(R570 vGPU 18) | 570.195.03(All versions prior to and including vGPU software 18.5) | 570.211.01(vGPU software 18.6) |
| CVE-2025-33219 | Guest driver | Linux(R535 vGPU 16) | 535.274.02(All versions prior to and including vGPU software 16.12) | 535.288.01(vGPU software 16.13) |
| CVE-2025-33219 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 19) | 580.105.06(All versions prior to and including vGPU software 19.3) | 580.129.08(vGPU software 19.4) |
| CVE-2025-33219 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 18) | 570.195.02(All versions prior to and including vGPU software 18.5) | 570.211.01(vGPU software 18.6) |
| CVE-2025-33219 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 16) | 535.274.03(All versions prior to and including vGPU software 16.12) | 535.288.01(vGPU software 16.13) |
| CVE-2025-33219 | Guest driver | Linux(Gaming) | 580.105.08(All versions up to and including the November 2025 release) | 590.48.01(December 2025 Release) |
| CVE-2025-33219 | Virtual GPU Manager | Red Hat Enterprise Linux KVM, VMware vSphere(Gaming) | 580.105.06(All versions up to and including the November 2025 release) | 590.48.01(December 2025 Release) |
| CVE-2025-33220 | GeForce | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33220 | GeForce | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33220 | GeForce | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33220 | GeForce | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33220 | NVIDIA RTX PRO, RTX, Quadro | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33220 | NVIDIA RTX PRO, RTX, Quadro | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33220 | NVIDIA RTX PRO, RTX, Quadro | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33220 | NVIDIA RTX PRO, RTX, Quadro | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33220 | Tesla | Linux(R590) | All driver versions prior to 590.48.01 | 590.48.01 |
| CVE-2025-33220 | Tesla | Linux(R580) | All driver versions prior to 580.126.09 | 580.126.09 |
| CVE-2025-33220 | Tesla | Linux(R570) | All driver versions prior to 570.211.01 | 570.211.01 |
| CVE-2025-33220 | Tesla | Linux(R535) | All driver versions prior to 535.288.01 | 535.288.01 |
| CVE-2025-33220 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 19) | 580.105.06(All versions prior to and including vGPU software 19.3) | 580.129.08(vGPU software 19.4) |
| CVE-2025-33220 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 18) | 570.195.02(All versions prior to and including vGPU software 18.5) | 570.211.01(vGPU software 19.4) |
| CVE-2025-33220 | Virtual GPU Manager | XenServer, VMware vSphere, Red Hat Enterprise Linux KVM, Ubuntu(vGPU 16) | 535.274.03(All versions prior to and including vGPU software 16.13) | 535.288.01(vGPU software 19.4) |

