# Vulcan

Vulcan is a framework for enterprise collaboration platforms originally created
for the DARPA Adaptive Vehicle Make (AVM) Program.  There, it provded a foundation
for VehicleFORGE, a platform for cyber-physical system design used to host
AVM's Fast Adaptive Next-Generation (FANG) vehicle design challenges.

VehicleFORGE originated as an early fork of SourceForge's Allura platform, which
is today Apache Allura.  Vulcan was motivated by providing a better organization
as a framework and by adding new forms of extensibility for adapting platform features
and services to an enterprise.

Vulcan is comprised of a core part and a set of optional annexes.
**This repository provides the VulcanWorkflow annex, which addresses support for
inter-team collaboration.**

## Micro-Service Dependencies

Vulcan employs MongoDB for document persistence, Apache Solr for indexing, and Redis
as a key-object store.  In the current release, the following versions of these
dependencies are known to be compatible:

  - MongoDB 3.4.4
  - Apache Solr 6.5.0
  - Redis 3.2.8

Vulcan applications assume these micro-services are deployed in a manner reflecting
the application's requirements.  Deployments of Apache Solr are supported by assets
provided in the *solr\_config* directory.

## Cloud Object Storage

Vulcan employs cloud object storage for artifact persistence, requiring an object
service supporting an AWS S3-compatible API that is accessed via the Python *boto*
package.  This requirement has been satisfied in private cloud deployments using
OpenStack Swift, for example.

## Workflow Extensions

The VulcanWorkflow framework annex focuses on extensions to Vulcan's basic project 
hosting features concerning collaborations among teams.  The annex introduces
a new kind of project-like construct, a *WorkflowStep*, whose creation is
initiated from a team and where other teams can be invited to participate.
Administrators from each participating team manage membership in the WorkflowStep
for their teams.  Automatically created and assigned roles allow tools in a
WorkflowStep to be authorized according to participating teams. 

# Release Notes

## Version 2.0.1

Minor Python packaging changes.

## Version 2.0.0

This release is compatible with the Ubuntu Xenial LTS.

 - New in Vulcan 2.0.0.
