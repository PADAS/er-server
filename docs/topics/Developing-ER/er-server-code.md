# ER Server Code

ER Server (aka DAS) is developed using the Django Web Services framework. Each component or service is known as a Django Project. For instance "activity" is a Django project which encompasses events and patrols. As we develop features for the various services, we want to loosely couple code between services as much as possible as well as minimize dependencies between services.

The following are the services that make up ER Server. There are a few projects for example "core" and "utils" which were set up to reduce cross dependencies or to host common code. "Core" as a true Django project is meant to hold common Django constructs, for example serializers or models that are unique to ER Server, but need to be shared between multiple projects. "utils" is there to hold utility code. Utility code could be used in another Django or even pure python project.

## accounts

## activity

## analyzers

## choices

## core

Project to host Django code that can be shared with multiple projects. We say Django code in that it relies on the Django app handling, including migrations, static files, etc. By putting code here, we are avoiding taking unnecessary dependencies.

## das_server

The Django app project. All of ER Server is started from here. This project hosts the settings and status of the ER server.

## file_uploads

## image_fileuploads

## mapping

## observations

## reports

## revision

## rt_api

## sensors

## tracking

## usercontent

## util_scripts

## utils

Not a true Django project. Instead this package hosts modules we can share across projects. It's okay that a module takes a Django dependency, but should not take a dependency on any other ER server project. Ideally, we could take any of the modules out of here and place them in a new Django project. Same for pure python modules, that we could make a library out of them and share to any other project.

## Deprecated Projects

### ste

### vectronics
