# Kestrel K2 Delivery Drone: Programme Specification

**Document:** TWR-K2-SPEC, version 1.4 (fictional test document for experiment E2; Tindleworth Robotics and Kestrel K2 are invented)
**Status:** Approved for pilot

## 1. Introduction
This section describes the overall scope for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the overall scope require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 
The Kestrel K2 is a small electric quadcopter for last-mile parcel delivery in dense city neighbourhoods. It succeeds the K1 prototype.


## 2. Stakeholders and roles

This section describes the stakeholders and roles for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the stakeholders and roles require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the stakeholders and roles interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the stakeholders and roles interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-001 | landing gear | The flight controller shall limit a single sensor dropout. | test |
| REQ-002 | logging service | The ground station shall tolerate hourly health summaries. | test |
| REQ-003 | maintenance app | The ground station shall log a single sensor dropout. | test |
| REQ-004 | GNSS receiver | The GNSS receiver shall tolerate a loss of uplink for 30 seconds. | test |
| REQ-005 | ground station | The GNSS receiver shall report rain at the intensity defined in test plan TP-7. | test |
| REQ-006 | telemetry radio | The battery management system shall report rain at the intensity defined in test plan TP-7. | demonstration |
| REQ-007 | airframe | The telemetry radio shall report encrypted maintenance logs. | analysis |
| REQ-008 | payload bay | The GNSS receiver shall support encrypted maintenance logs. | test |
| REQ-009 | charging dock | The payload bay shall support vibration up to the level in Annex C. | analysis |
| REQ-010 | landing gear | The propulsion shall tolerate rain at the intensity defined in test plan TP-7. | test |
| REQ-011 | charging dock | The telemetry radio shall verify encrypted maintenance logs. | demonstration |
| REQ-012 | status LEDs | The landing gear shall verify rain at the intensity defined in test plan TP-7. | demonstration |
| REQ-013 | landing gear | The payload bay shall log firmware rollback to the previous release. | analysis |
| REQ-014 | propulsion | The charging dock shall recover from encrypted maintenance logs. | demonstration |
| REQ-015 | maintenance app | The landing gear shall verify operator overrides from the ground station. | test |
| REQ-016 | propulsion | The ground station shall limit firmware rollback to the previous release. | inspection |
| REQ-017 | flight controller | The maintenance app shall verify temperature drift within the calibrated band. | test |
| REQ-018 | battery management system | The propulsion shall expose hourly health summaries. | inspection |
| REQ-019 | charging dock | The obstacle sensor shall verify vibration up to the level in Annex C. | test |
| REQ-020 | payload bay | The obstacle sensor shall tolerate a single sensor dropout. | inspection |
| REQ-021 | battery management system | The charging dock shall verify operator overrides from the ground station. | demonstration |
| REQ-022 | maintenance app | The battery management system shall expose a single sensor dropout. | demonstration |


## 3. Operating concept

This section describes the operating concept for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the operating concept require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the operating concept interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the operating concept interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-023 | landing gear | The flight controller shall tolerate a corrupted configuration file. | test |
| REQ-024 | telemetry radio | The status LEDs shall recover from firmware rollback to the previous release. | analysis |
| REQ-025 | GNSS receiver | The GNSS receiver shall verify vibration up to the level in Annex C. | analysis |
| REQ-026 | obstacle sensor | The GNSS receiver shall recover from firmware rollback to the previous release. | demonstration |
| REQ-027 | logging service | The ground station shall recover from temperature drift within the calibrated band. | inspection |
| REQ-028 | battery management system | The maintenance app shall limit a loss of uplink for 30 seconds. | analysis |
| REQ-029 | propulsion | The flight controller shall support a loss of uplink for 30 seconds. | analysis |
| REQ-030 | airframe | The obstacle sensor shall support operator overrides from the ground station. | inspection |
| REQ-031 | airframe | The flight controller shall limit encrypted maintenance logs. | inspection |
| REQ-032 | charging dock | The charging dock shall expose firmware rollback to the previous release. | test |
| REQ-033 | obstacle sensor | The maintenance app shall limit temperature drift within the calibrated band. | demonstration |
| REQ-034 | GNSS receiver | The propulsion shall verify temperature drift within the calibrated band. | test |
| REQ-035 | telemetry radio | The propulsion shall log a corrupted configuration file. | analysis |
| REQ-036 | propulsion | The landing gear shall report vibration up to the level in Annex C. | test |
| REQ-037 | charging dock | The flight controller shall tolerate hourly health summaries. | test |
| REQ-038 | propulsion | The logging service shall log rain at the intensity defined in test plan TP-7. | demonstration |
| REQ-039 | flight controller | The battery management system shall recover from hourly health summaries. | inspection |
| REQ-040 | obstacle sensor | The propulsion shall tolerate a corrupted configuration file. | demonstration |
| REQ-041 | obstacle sensor | The obstacle sensor shall recover from vibration up to the level in Annex C. | analysis |
| REQ-042 | propulsion | The parachute module shall expose operator overrides from the ground station. | demonstration |
| REQ-043 | logging service | The parachute module shall support encrypted maintenance logs. | test |
| REQ-044 | telemetry radio | The ground station shall expose firmware rollback to the previous release. | test |


## 4. Airframe

This section describes the airframe for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the airframe require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the airframe interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the airframe interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-045 | status LEDs | The ground station shall recover from vibration up to the level in Annex C. | inspection |
| REQ-046 | ground station | The landing gear shall support hourly health summaries. | analysis |
| REQ-047 | ground station | The ground station shall expose a loss of uplink for 30 seconds. | analysis |
| REQ-048 | status LEDs | The telemetry radio shall limit a loss of uplink for 30 seconds. | analysis |
| REQ-049 | ground station | The obstacle sensor shall expose a single sensor dropout. | test |
| REQ-050 | status LEDs | The payload bay shall verify operator overrides from the ground station. | analysis |
| REQ-051 | parachute module | The charging dock shall expose a corrupted configuration file. | inspection |
| REQ-052 | landing gear | The propulsion shall log vibration up to the level in Annex C. | analysis |
| REQ-053 | obstacle sensor | The telemetry radio shall expose a loss of uplink for 30 seconds. | demonstration |
| REQ-054 | charging dock | The maintenance app shall report a corrupted configuration file. | inspection |
| REQ-055 | status LEDs | The battery management system shall tolerate vibration up to the level in Annex C. | demonstration |
| REQ-056 | status LEDs | The parachute module shall log a corrupted configuration file. | analysis |
| REQ-057 | GNSS receiver | The status LEDs shall expose vibration up to the level in Annex C. | demonstration |
| REQ-058 | obstacle sensor | The GNSS receiver shall tolerate firmware rollback to the previous release. | analysis |
| REQ-059 | flight controller | The airframe shall support rain at the intensity defined in test plan TP-7. | demonstration |
| REQ-060 | status LEDs | The battery management system shall support rain at the intensity defined in test plan TP-7. | demonstration |
| REQ-061 | battery management system | The maintenance app shall expose firmware rollback to the previous release. | analysis |
| REQ-062 | airframe | The airframe shall tolerate encrypted maintenance logs. | analysis |
| REQ-063 | GNSS receiver | The logging service shall log a loss of uplink for 30 seconds. | test |
| REQ-064 | payload bay | The telemetry radio shall recover from encrypted maintenance logs. | analysis |
| REQ-065 | status LEDs | The charging dock shall expose operator overrides from the ground station. | demonstration |
| REQ-066 | logging service | The flight controller shall report hourly health summaries. | demonstration |


## 5. Propulsion

This section describes the propulsion for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the propulsion require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the propulsion interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the propulsion interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-067 | battery management system | The charging dock shall limit encrypted maintenance logs. | analysis |
| REQ-068 | ground station | The flight controller shall report a corrupted configuration file. | analysis |
| REQ-069 | charging dock | The airframe shall support firmware rollback to the previous release. | analysis |
| REQ-070 | obstacle sensor | The charging dock shall tolerate encrypted maintenance logs. | test |
| REQ-071 | landing gear | The battery management system shall verify vibration up to the level in Annex C. | test |
| REQ-072 | telemetry radio | The telemetry radio shall recover from a single sensor dropout. | test |
| REQ-073 | ground station | The obstacle sensor shall report vibration up to the level in Annex C. | demonstration |
| REQ-074 | landing gear | The charging dock shall log operator overrides from the ground station. | demonstration |
| REQ-075 | ground station | The ground station shall verify encrypted maintenance logs. | analysis |
| REQ-076 | parachute module | The ground station shall recover from encrypted maintenance logs. | analysis |
| REQ-077 | logging service | The obstacle sensor shall support temperature drift within the calibrated band. | test |
| REQ-078 | GNSS receiver | The obstacle sensor shall expose vibration up to the level in Annex C. | analysis |
| REQ-079 | GNSS receiver | The propulsion shall log operator overrides from the ground station. | test |
| REQ-080 | maintenance app | The status LEDs shall support hourly health summaries. | analysis |
| REQ-081 | payload bay | The maintenance app shall support a corrupted configuration file. | analysis |
| REQ-082 | parachute module | The propulsion shall limit a corrupted configuration file. | analysis |
| REQ-083 | battery management system | The logging service shall log firmware rollback to the previous release. | demonstration |
| REQ-084 | ground station | The GNSS receiver shall expose temperature drift within the calibrated band. | analysis |
| REQ-085 | landing gear | The landing gear shall tolerate hourly health summaries. | test |
| REQ-086 | landing gear | The ground station shall verify a corrupted configuration file. | test |
| REQ-087 | GNSS receiver | The landing gear shall recover from encrypted maintenance logs. | test |
| REQ-088 | propulsion | The maintenance app shall log vibration up to the level in Annex C. | test |


## 6. Flight control

This section describes the flight control for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the flight control require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the flight control interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the flight control interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-089 | payload bay | The payload bay shall report firmware rollback to the previous release. | inspection |
| REQ-090 | status LEDs | The flight controller shall limit operator overrides from the ground station. | demonstration |
| REQ-091 | flight controller | The ground station shall verify hourly health summaries. | test |
| REQ-092 | payload bay | The airframe shall support temperature drift within the calibrated band. | test |
| REQ-093 | payload bay | The airframe shall tolerate operator overrides from the ground station. | test |
| REQ-094 | charging dock | The logging service shall log vibration up to the level in Annex C. | inspection |
| REQ-095 | logging service | The propulsion shall verify a single sensor dropout. | inspection |
| REQ-096 | ground station | The GNSS receiver shall recover from rain at the intensity defined in test plan TP-7. | analysis |
| REQ-097 | airframe | The ground station shall log vibration up to the level in Annex C. | analysis |
| REQ-098 | payload bay | The airframe shall support a loss of uplink for 30 seconds. | inspection |
| REQ-099 | battery management system | The payload bay shall log operator overrides from the ground station. | demonstration |
| REQ-100 | ground station | The battery management system shall support operator overrides from the ground station. | inspection |
| REQ-101 | status LEDs | The airframe shall recover from a single sensor dropout. | test |
| REQ-102 | airframe | The parachute module shall log encrypted maintenance logs. | demonstration |
| REQ-103 | telemetry radio | The maintenance app shall verify vibration up to the level in Annex C. | demonstration |
| REQ-104 | battery management system | The obstacle sensor shall limit encrypted maintenance logs. | inspection |
| REQ-105 | parachute module | The telemetry radio shall log hourly health summaries. | analysis |
| REQ-106 | logging service | The maintenance app shall support temperature drift within the calibrated band. | inspection |
| REQ-107 | airframe | The logging service shall support a single sensor dropout. | test |
| REQ-108 | battery management system | The parachute module shall recover from temperature drift within the calibrated band. | analysis |
| REQ-109 | airframe | The propulsion shall limit encrypted maintenance logs. | inspection |
| REQ-110 | charging dock | The telemetry radio shall recover from a single sensor dropout. | demonstration |


## 7. Communications

This section describes the communications for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the communications require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the communications interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the communications interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-111 | flight controller | The flight controller shall recover from a corrupted configuration file. | test |
| REQ-112 | payload bay | The landing gear shall expose encrypted maintenance logs. | inspection |
| REQ-113 | telemetry radio | The airframe shall recover from a loss of uplink for 30 seconds. | inspection |
| REQ-114 | flight controller | The airframe shall expose temperature drift within the calibrated band. | test |
| REQ-115 | obstacle sensor | The payload bay shall log a loss of uplink for 30 seconds. | test |
| REQ-116 | propulsion | The payload bay shall tolerate firmware rollback to the previous release. | demonstration |
| REQ-117 | charging dock | The airframe shall limit a single sensor dropout. | inspection |
| REQ-118 | payload bay | The battery management system shall log vibration up to the level in Annex C. | analysis |
| REQ-119 | battery management system | The maintenance app shall limit hourly health summaries. | demonstration |
| REQ-120 | flight controller | The payload bay shall support a single sensor dropout. | demonstration |
| REQ-121 | parachute module | The parachute module shall support encrypted maintenance logs. | test |
| REQ-122 | logging service | The battery management system shall log vibration up to the level in Annex C. | test |
| REQ-123 | airframe | The flight controller shall expose vibration up to the level in Annex C. | demonstration |
| REQ-124 | logging service | The obstacle sensor shall report a single sensor dropout. | analysis |
| REQ-125 | obstacle sensor | The payload bay shall report a corrupted configuration file. | test |
| REQ-126 | parachute module | The maintenance app shall tolerate encrypted maintenance logs. | test |
| REQ-127 | parachute module | The parachute module shall verify operator overrides from the ground station. | test |
| REQ-128 | logging service | The payload bay shall log a loss of uplink for 30 seconds. | analysis |
| REQ-129 | parachute module | The battery management system shall verify a corrupted configuration file. | demonstration |
| REQ-130 | propulsion | The obstacle sensor shall recover from a single sensor dropout. | analysis |
| REQ-131 | propulsion | The charging dock shall support hourly health summaries. | inspection |
| REQ-132 | battery management system | The parachute module shall recover from rain at the intensity defined in test plan TP-7. | analysis |


## 8. Payload

This section describes the payload for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the payload require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the payload interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the payload interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-133 | airframe | The obstacle sensor shall report a corrupted configuration file. | inspection |
| REQ-134 | battery management system | The propulsion shall log a corrupted configuration file. | inspection |
| REQ-135 | parachute module | The ground station shall recover from a corrupted configuration file. | demonstration |
| REQ-136 | obstacle sensor | The status LEDs shall tolerate encrypted maintenance logs. | analysis |
| REQ-137 | payload bay | The propulsion shall verify a single sensor dropout. | inspection |
| REQ-138 | obstacle sensor | The propulsion shall verify operator overrides from the ground station. | demonstration |
| REQ-139 | telemetry radio | The maintenance app shall log vibration up to the level in Annex C. | test |
| REQ-140 | flight controller | The parachute module shall recover from hourly health summaries. | analysis |
| REQ-141 | charging dock | The logging service shall recover from vibration up to the level in Annex C. | inspection |
| REQ-142 | telemetry radio | The obstacle sensor shall verify temperature drift within the calibrated band. | test |
| REQ-143 | flight controller | The airframe shall verify a corrupted configuration file. | demonstration |
| REQ-144 | payload bay | The parachute module shall support temperature drift within the calibrated band. | inspection |
| REQ-145 | GNSS receiver | The landing gear shall tolerate hourly health summaries. | test |
| REQ-146 | landing gear | The status LEDs shall expose temperature drift within the calibrated band. | test |
| REQ-147 | maintenance app | The telemetry radio shall report operator overrides from the ground station. | inspection |
| REQ-148 | landing gear | The propulsion shall limit temperature drift within the calibrated band. | test |
| REQ-149 | landing gear | The maintenance app shall limit operator overrides from the ground station. | test |
| REQ-150 | payload bay | The propulsion shall report operator overrides from the ground station. | analysis |
| REQ-151 | telemetry radio | The payload bay shall limit encrypted maintenance logs. | inspection |
| REQ-152 | telemetry radio | The status LEDs shall expose temperature drift within the calibrated band. | test |
| REQ-153 | status LEDs | The status LEDs shall limit encrypted maintenance logs. | analysis |
| REQ-154 | parachute module | The propulsion shall report temperature drift within the calibrated band. | demonstration |


### 8.3 Payload limits

The certified maximum payload of the Kestrel K2 is **3.8 kg**, including the parcel box. Above 3.2 kg the flight controller reduces the maximum range by 20 percent.


## 9. Energy and batteries

This section describes the energy and batteries for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the energy and batteries require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the energy and batteries interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the energy and batteries interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-155 | charging dock | The status LEDs shall support operator overrides from the ground station. | demonstration |
| REQ-156 | airframe | The maintenance app shall support firmware rollback to the previous release. | demonstration |
| REQ-157 | GNSS receiver | The landing gear shall recover from operator overrides from the ground station. | inspection |
| REQ-158 | parachute module | The parachute module shall recover from temperature drift within the calibrated band. | analysis |
| REQ-159 | payload bay | The obstacle sensor shall limit vibration up to the level in Annex C. | analysis |
| REQ-160 | battery management system | The flight controller shall tolerate a loss of uplink for 30 seconds. | demonstration |
| REQ-161 | ground station | The telemetry radio shall verify hourly health summaries. | demonstration |
| REQ-162 | GNSS receiver | The flight controller shall log a loss of uplink for 30 seconds. | test |
| REQ-163 | flight controller | The landing gear shall tolerate hourly health summaries. | analysis |
| REQ-164 | landing gear | The payload bay shall log a single sensor dropout. | demonstration |
| REQ-165 | GNSS receiver | The GNSS receiver shall log temperature drift within the calibrated band. | inspection |
| REQ-166 | landing gear | The status LEDs shall report a corrupted configuration file. | inspection |
| REQ-167 | charging dock | The landing gear shall support encrypted maintenance logs. | analysis |
| REQ-168 | propulsion | The payload bay shall log temperature drift within the calibrated band. | demonstration |
| REQ-169 | battery management system | The obstacle sensor shall limit operator overrides from the ground station. | test |
| REQ-170 | flight controller | The airframe shall limit a corrupted configuration file. | demonstration |
| REQ-171 | airframe | The propulsion shall limit encrypted maintenance logs. | demonstration |
| REQ-172 | obstacle sensor | The telemetry radio shall tolerate a loss of uplink for 30 seconds. | analysis |
| REQ-173 | flight controller | The ground station shall tolerate a corrupted configuration file. | test |
| REQ-174 | ground station | The status LEDs shall report a single sensor dropout. | analysis |
| REQ-175 | telemetry radio | The charging dock shall report operator overrides from the ground station. | analysis |
| REQ-176 | battery management system | The payload bay shall limit vibration up to the level in Annex C. | test |


### 9.4 Cold-weather operation

After the battery test campaign, the minimum operating temperature was set to **minus 12 degrees Celsius**. Below that, the battery management system refuses to arm the motors.


## 10. Software and firmware

This section describes the software and firmware for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the software and firmware require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the software and firmware interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the software and firmware interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-177 | propulsion | The payload bay shall log temperature drift within the calibrated band. | inspection |
| REQ-178 | telemetry radio | The status LEDs shall report a single sensor dropout. | inspection |
| REQ-179 | obstacle sensor | The payload bay shall expose a loss of uplink for 30 seconds. | demonstration |
| REQ-180 | ground station | The telemetry radio shall log a single sensor dropout. | demonstration |
| REQ-181 | parachute module | The battery management system shall recover from a single sensor dropout. | test |
| REQ-182 | telemetry radio | The obstacle sensor shall limit vibration up to the level in Annex C. | inspection |
| REQ-183 | telemetry radio | The battery management system shall limit hourly health summaries. | analysis |
| REQ-184 | obstacle sensor | The airframe shall expose temperature drift within the calibrated band. | inspection |
| REQ-185 | battery management system | The GNSS receiver shall log a single sensor dropout. | inspection |
| REQ-186 | parachute module | The logging service shall tolerate a loss of uplink for 30 seconds. | demonstration |
| REQ-187 | telemetry radio | The payload bay shall log a loss of uplink for 30 seconds. | demonstration |
| REQ-188 | telemetry radio | The payload bay shall recover from vibration up to the level in Annex C. | demonstration |
| REQ-189 | charging dock | The flight controller shall log a corrupted configuration file. | demonstration |
| REQ-190 | maintenance app | The battery management system shall report rain at the intensity defined in test plan TP-7. | analysis |
| REQ-191 | maintenance app | The GNSS receiver shall report a loss of uplink for 30 seconds. | test |
| REQ-192 | charging dock | The flight controller shall limit a single sensor dropout. | test |
| REQ-193 | flight controller | The GNSS receiver shall verify hourly health summaries. | test |
| REQ-194 | propulsion | The maintenance app shall support hourly health summaries. | analysis |
| REQ-195 | flight controller | The battery management system shall verify a single sensor dropout. | inspection |
| REQ-196 | battery management system | The parachute module shall limit hourly health summaries. | inspection |
| REQ-197 | obstacle sensor | The flight controller shall tolerate a single sensor dropout. | test |
| REQ-198 | payload bay | The propulsion shall expose temperature drift within the calibrated band. | test |


### 10.6 Release plan

The **firmware freeze for release FW 3.2 is 9 February 2027**. After the freeze only safety fixes approved by the design authority may be merged. FW 3.2 is the release that will fly in the city pilot.


## 11. Test and certification

This section describes the test and certification for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the test and certification require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the test and certification interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the test and certification interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-199 | ground station | The status LEDs shall log temperature drift within the calibrated band. | inspection |
| REQ-200 | status LEDs | The logging service shall recover from temperature drift within the calibrated band. | test |
| REQ-201 | airframe | The parachute module shall verify a loss of uplink for 30 seconds. | inspection |
| REQ-202 | ground station | The maintenance app shall verify a loss of uplink for 30 seconds. | inspection |
| REQ-203 | landing gear | The parachute module shall verify a single sensor dropout. | demonstration |
| REQ-204 | telemetry radio | The status LEDs shall limit a single sensor dropout. | demonstration |
| REQ-205 | airframe | The obstacle sensor shall tolerate a single sensor dropout. | inspection |
| REQ-206 | telemetry radio | The parachute module shall tolerate rain at the intensity defined in test plan TP-7. | inspection |
| REQ-207 | landing gear | The payload bay shall expose rain at the intensity defined in test plan TP-7. | test |
| REQ-208 | payload bay | The parachute module shall expose operator overrides from the ground station. | inspection |
| REQ-209 | airframe | The parachute module shall tolerate a single sensor dropout. | analysis |
| REQ-210 | propulsion | The obstacle sensor shall verify temperature drift within the calibrated band. | inspection |
| REQ-211 | maintenance app | The GNSS receiver shall verify firmware rollback to the previous release. | demonstration |
| REQ-212 | flight controller | The airframe shall recover from firmware rollback to the previous release. | analysis |
| REQ-213 | landing gear | The logging service shall expose a corrupted configuration file. | inspection |
| REQ-214 | status LEDs | The status LEDs shall tolerate encrypted maintenance logs. | analysis |
| REQ-215 | GNSS receiver | The status LEDs shall support a loss of uplink for 30 seconds. | demonstration |
| REQ-216 | propulsion | The battery management system shall report a corrupted configuration file. | inspection |
| REQ-217 | flight controller | The GNSS receiver shall tolerate vibration up to the level in Annex C. | inspection |
| REQ-218 | charging dock | The propulsion shall log vibration up to the level in Annex C. | demonstration |
| REQ-219 | obstacle sensor | The parachute module shall verify firmware rollback to the previous release. | analysis |
| REQ-220 | flight controller | The GNSS receiver shall verify rain at the intensity defined in test plan TP-7. | analysis |


## 12. Programme schedule

This section describes the programme schedule for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the programme schedule require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

This section describes the programme schedule interfaces for the Kestrel K2 programme. It is written for engineers, test leads and the programme office. Unless stated otherwise, values are nominal and apply at sea level in still air. Changes to the programme schedule interfaces require a change request reviewed by the design authority. Earlier drafts of this document (v0.3 to v0.7) used different numbering; the requirement IDs below are now stable and must be quoted in test reports. 

| ID | Subsystem | Requirement | Verification |
|---|---|---|---|
| REQ-221 | parachute module | The ground station shall tolerate operator overrides from the ground station. | inspection |
| REQ-222 | payload bay | The charging dock shall recover from hourly health summaries. | inspection |
| REQ-223 | parachute module | The payload bay shall log a corrupted configuration file. | analysis |
| REQ-224 | flight controller | The telemetry radio shall log firmware rollback to the previous release. | inspection |
| REQ-225 | maintenance app | The maintenance app shall log hourly health summaries. | test |
| REQ-226 | GNSS receiver | The payload bay shall log encrypted maintenance logs. | analysis |
| REQ-227 | battery management system | The status LEDs shall tolerate a corrupted configuration file. | test |
| REQ-228 | propulsion | The airframe shall verify a loss of uplink for 30 seconds. | demonstration |
| REQ-229 | maintenance app | The landing gear shall report operator overrides from the ground station. | analysis |
| REQ-230 | propulsion | The airframe shall log rain at the intensity defined in test plan TP-7. | analysis |
| REQ-231 | maintenance app | The propulsion shall expose encrypted maintenance logs. | analysis |
| REQ-232 | obstacle sensor | The charging dock shall recover from a single sensor dropout. | test |
| REQ-233 | battery management system | The charging dock shall expose a loss of uplink for 30 seconds. | test |
| REQ-234 | landing gear | The landing gear shall support a single sensor dropout. | analysis |
| REQ-235 | payload bay | The airframe shall log a single sensor dropout. | inspection |
| REQ-236 | GNSS receiver | The battery management system shall expose firmware rollback to the previous release. | inspection |
| REQ-237 | propulsion | The telemetry radio shall report a corrupted configuration file. | demonstration |
| REQ-238 | propulsion | The GNSS receiver shall tolerate temperature drift within the calibrated band. | analysis |
| REQ-239 | battery management system | The ground station shall tolerate firmware rollback to the previous release. | demonstration |
| REQ-240 | parachute module | The payload bay shall limit operator overrides from the ground station. | inspection |
| REQ-241 | GNSS receiver | The airframe shall recover from rain at the intensity defined in test plan TP-7. | inspection |
| REQ-242 | GNSS receiver | The GNSS receiver shall report hourly health summaries. | analysis |


### 12.2 Delivery lead time

Production drones ship **six weeks** after a purchase order is confirmed. Pilot customers get priority slots.

