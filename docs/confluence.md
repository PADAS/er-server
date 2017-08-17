# Converting Confluence WIKI to Markdown

We used the java based app confluence2md to make this conversion.

See confluence2md[http://www.viaboxx.de/code/confluence2md/]

The following lists the root wiki pages in json:
[wiki root](https://vulcan.atlassian.net/wiki/rest/api/content)

We want to retrieve these pages:
[DAS Wiki](https://vulcan.atlassian.net/wiki/display/DASTS/DAS+Program)

DAS Wiki REST call
    https://vulcan.atlassian.net/wiki/rest/api/content/4292614
    which gives us the id=4292614

Here is the command run to import the DAS wiki:
    java -jar .\confluence2md-2.1-fat.jar -u <username:password> -o das.md +T true +H true +RootPageTitle true -server https://vulcan.atlassian.ne
t/wiki 4292614
     
