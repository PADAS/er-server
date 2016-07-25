Param(
  [string]$db_name = $(""),
  [string]$db_host = "at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com",
  [string]$user = "postgres",
  [string]$ownerpw = "dasdb_owner",
  [string]$userpw = "dasdb_user"
)

if($db_name -like $("")){
  throw "db_name (-db_name) param required."
}

psql -h $db_host -U $user -v ownerpw="'$ownerpw'" -v userpw="'$userpw'" -v db_name="$db_name" -f .\update_db_users.sql --set ON_ERROR_STOP=on
