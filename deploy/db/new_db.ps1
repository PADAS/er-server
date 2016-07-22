Param(
  [string]$db_name = $(""),
  [string]$db_host = "at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com",
  [string]$user = "postgres",
  [string]$type = "dev",
  [string]$ownerpw = "dasdb_owner",
  [string]$userpw = "dasdb_user"
)

if($db_name -like $("")){
      throw "db_name (-db_name) param required."
    }

if($db_type -eq "prod") {
    psql -h $db_host -U $user -v ownerpw="$ownerpw" -v userpw="$userpw" -v db_name="$db_name" -f .\new_prod_db.sql --set ON_ERROR_STOP=on
}
else {
    psql -h $db_host -U $user -v db_name="$db_name" -f .\new_db.sql --set ON_ERROR_STOP=on
}
