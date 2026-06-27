# AG dependency migration plan

This file contains a list of changes to apply to the project(s) in this repo. Combine it with your knowledge of the coding conventions and verification tools available for this project to plan and execute an update. After applying these changes use the appropriate tools at your disposal to validate that the changes were successful, such as running the build, typechecking, tests, and starting the dev server and accessing it with a browser.

## Scope

See [./AG_UPDATE_SCOPE.md] for project(s) to apply these changes to and the affected dependencies.

# Grid

## Grid v35.x -> v36.x

### BREAKING: Minimum TypeScript version is now 5.8.3

Change: The minimum TypeScript version is now 5.8.3 across all frameworks. (The project currently depends on TypeScript `^5.7.2`.)
Mitigation: Raise the project's TypeScript dependency to `>= 5.8.3` and re-run typechecking.

# Charts

## Charts v13.x -> v14.x

### BREAKING: Minimum TypeScript version is now 5.8

Change: The minimum supported version of TypeScript for AG Charts is now 5.8.
Mitigation: Raise TypeScript to `>= 5.8`. This is already satisfied by the Grid v36 requirement of TypeScript `>= 5.8.3` above — no additional action beyond that bump.
